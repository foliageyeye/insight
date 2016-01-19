# -*- coding:utf-8 -*-

# Python imports
import os
import concurrent.futures
import bcrypt
import json
from datetime import datetime
# Tornado imports
import tornado.auth
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web

from tornado.options import define, options
from tornado.web import url
from tornado import gen, websocket
# Sqlalchemy imports
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

# App imports
import models
import uimodules
import util

executor = concurrent.futures.ThreadPoolExecutor(2)
# Options
define("port", default=8888, help="run on the given port", type=int)
define("debug", default=True, type=bool)
define("db_path", default='sqlite:///./insight.db', type=str)


class Application(tornado.web.Application):

    def __init__(self):
        handlers = [
            url(r"/", IndexHandler, name='index'),
            url(r"/events", EventsHandler, name='events'),
            url(r"/visualization", VisualizationHandler, name='visualization'),
            # location configuration
            url(r"/locations", LocationHandler, name='locations'),
            url(r"/locations/setup", LocationSetupHandler,
                name='location_setup'),
            url(r"/locations/add", LocationAddHandler,
                name='location_add'),
            url(r"/locations/remove", LocationRemoveHandler,
                name='department_remove'),
            # department configuration
            url(r"/departments", DepartmentHandler, name='departments'),
            url(r"/departments/setup", DepartmentSetupHandler,
                name='department_setup'),
            url(r"/departments/add", DepartmentAddHandler,
                name='location_add'),
            url(r"/departments/remove", DepartmentRemoveHandler,
                name='department_remove'),
            # statistcs configuration
            url(r"/statistics", StatisticsHandler, name='statistics'),
            # auth configuration
            url(r"/auth/create", AuthCreateHandler),
            url(r"/auth/login", AuthLoginHandler),
            url(r"/auth/logout", AuthLogoutHandler),
            url(r"/auth/profile", AuthProfileHandler),
            # web socket
            url(r'/ws', SocketHandler),
            url(r'/ws_global', GlobalSocketHandler),
            # web service api
            url(r'/api', ApiHandler),
        ]
        settings = dict(
            debug=options.debug,
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            template_path=os.path.join(os.path.dirname(__file__), 'templates'),
            xsrf_cookies=False,
            # TODO Change this to a random string
            cookie_secret="nzjxcjasduuqwheazmu=",
            ui_modules=uimodules,
            login_url="/auth/login",
        )
        tornado.web.Application.__init__(self, handlers, **settings)
        engine = create_engine(
            options.db_path, convert_unicode=True, echo=options.debug)
        models.init_db(engine)
        self.db = scoped_session(sessionmaker(bind=engine))


class BaseHandler(tornado.web.RequestHandler):

    @property
    def db(self):
        return self.application.db

    def get_current_user(self):
        name = self.get_secure_cookie("platform_user")
        if not name:
            return None
        return self.db.query(models.User).filter_by(name=name).first()

    def any_user_exists(self):
        print self.db.query(models.User).first()
        return bool(self.db.query(models.User).first())


class IndexHandler(BaseHandler):

    @tornado.web.authenticated
    def get(self):
        user = self.db.query(models.User).first()
        events = self.db.query(models.Event).filter_by(status=0).all()
        e_dic = {1:'交通拥堵', 2:'可疑事件', 3:'违章占道', 4:'交通事故' , 5:'行人横穿马路'}
        data = []
        for e in events:
            location = self.db.query(models.Location).filter_by(id=e.location_id).one()
            data.append({'id':e.id, 'event_name':e_dic[e.id], 'location':location.name, 'dt': e.dt.strftime('%Y-%m-%d %H:%M:%S')})
        num_event = ''
        if events:
            num_event = len(events)
        self.render(
            'index.html', user=user, num_event=num_event, events=data)


class EventsHandler(BaseHandler):

    @tornado.web.authenticated
    def get(self):
        id = self.get_argument('id')
        event = self.db.query(models.Event).filter_by(id=id).one()
        location = self.db.query(models.Location).filter_by(id=event.location_id).one()
        e_dic = {1:'交通拥堵', 2:'可疑事件', 3:'违章占到', 4:'交通事道' , 5:'行人横穿马路'}       
        data  = {'status': 'success', 'location': location.name, '_event':e_dic[event.type], 'dt': event.dt.strftime('%Y-%m-%d %H:%M:%S'), 'snapshot': event.snapshot}
        print data
        self.write(data)
        
        


class VisualizationHandler(BaseHandler):
    @tornado.web.authenticated
    def get(self):
        # form = forms.HelloForm()
        user = self.db.query(models.User).first()
        locations = self.db.query(models.Location).all()
        num_event = util.getNewEventNum(self)
        self.render(
            'visualization.html',
            user=user,
            locations=locations,
            num_event=num_event)


class StatisticsHandler(BaseHandler):

    @tornado.web.authenticated
    def get(self):
        user = self.get_current_user()
        locations = self.db.query(models.Location).all()
        num_event = util.getNewEventNum(self)
        events = self.db.query(models.Event).all()
        self.render(
            'statistics.html',
            user=user,
            locations=locations,
            events=events,
            num_event=num_event)

    @tornado.web.authenticated
    def post(self):
        self.render('statistics.html')


class AuthCreateHandler(BaseHandler):

    def get(self):
        if self.any_user_exists():
            self.redirect("/auth/login")
        else:
            self.render("create_user.html")

    @gen.coroutine
    def post(self):
        if self.any_user_exists():
            raise tornado.web.HTTPError(400, "user already created")
        hashed_password = yield executor.submit(
            bcrypt.hashpw, tornado.escape.utf8(self.get_argument("password")),
            bcrypt.gensalt())

        ed_user = models.User(name=self.get_argument("name"),
                              password=hashed_password)
        self.db.add(ed_user)
        self.db.commit()
        self.set_secure_cookie("platform_user", str(ed_user.name))
        self.redirect("/")


class AuthLoginHandler(BaseHandler):

    def get(self):
        # If there are no authors, redirect to the account creation page.
        if not self.any_user_exists():
            self.redirect("/auth/create")
        else:
            self.render("login.html", error=None)

    @gen.coroutine
    def post(self):
        username = self.get_argument("name")
        user = self.db.query(models.User).filter_by(name=username).first()
        if not user:
            self.render("login.html", error="用户名不存在")
            return
        hashed_password = yield executor.submit(
            bcrypt.hashpw, tornado.escape.utf8(self.get_argument("password")),
            tornado.escape.utf8(user.password))
        if hashed_password == user.password:
            self.set_secure_cookie("platform_user", str(user.name))
            self.redirect("/")
        else:
            self.render("login.html", error="密码输入有误")


class AuthLogoutHandler(BaseHandler):

    @tornado.web.authenticated
    def get(self):
        self.clear_cookie("platform_user")
        self.redirect("/")


class AuthProfileHandler(BaseHandler):

    @tornado.web.authenticated
    def get(self):
        user = self.get_current_user()
        self.render('profile.html', user=user, error=None)

    @tornado.web.authenticated
    @gen.coroutine
    def post(self):
        user = self.get_current_user()
        name = self.get_argument("name")
        password1 = self.get_argument("password1")
        password2 = self.get_argument("password2")
        if len(name) < 1 or len(name) > 20:
            self.render('profile.html', user=user, error="username wrong")
        if len(password1) < 1 or len(password1) > 20 or password1 != password2:
            self.render('profile.html', user=user, error="password wrong")

        user.name = name
        user.fullname = name
        hashed_password = yield executor.submit(
            bcrypt.hashpw, tornado.escape.utf8(password1),
            tornado.escape.utf8(user.password))
        user.password = hashed_password
        self.db.commit()
        self.write(
            "<script>alert('管理员信息更新成功，请重新登录。');window.location ='/auth/logout'</script>")


class LocationHandler(BaseHandler):

    @tornado.web.authenticated
    def get(self):
        user = self.get_current_user()
        locations = self.db.query(models.Location).all()
        num_event = util.getNewEventNum(self)
        self.render('location.html',
                    user=user,
                    locations=locations,
                    num_event=num_event)


class LocationSetupHandler(BaseHandler):

    @tornado.web.authenticated
    def post(self):
        name = self.get_argument("name")
        id = self.get_argument("id")
        lng = self.get_argument("lng")
        lat = self.get_argument("lat")
        location = self.db.query(models.Location).filter_by(id=id).first()
        location.name = name
        location.lng = lng
        location.lat = lat
        self.db.commit()
        self.write('success')


class LocationRemoveHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        id = self.get_argument("id")
        location = self.db.query(models.Location).filter_by(id=id).one()
        self.db.delete(location)
        self.write('success')


class LocationAddHandler(BaseHandler):

    @tornado.web.authenticated
    def post(self):
        name = self.get_argument("name")
        lng = self.get_argument("lng")
        lat = self.get_argument("lat")
        location = models.Location(name=name,
                                   lng=lng,
                                   lat=lat)
        self.db.add(location)
        self.db.commit()
        print name, lng, lat
        self.write('success')


class DepartmentHandler(BaseHandler):

    @tornado.web.authenticated
    def get(self):
        num_event = None
        num_event = util.getNewEventNum(self)
        user = self.get_current_user()
        departments = self.db.query(models.Department).all()
        self.render('department.html',
                    user=user,
                    departments=departments,
                    num_event=num_event)


class DepartmentSetupHandler(BaseHandler):

    @tornado.web.authenticated
    def post(self):
        id = self.get_argument("id")
        name = self.get_argument("name")
        person = self.get_argument("person")
        phone = self.get_argument("phone")
        mobile = self.get_argument("mobile")
        email = self.get_argument("email")
        department = self.db.query(models.Department).filter_by(id=id).first()
        department.name = name
        department.person = person
        department.phone = phone
        department.mobile = mobile
        department.email = email
        self.db.commit()
        self.write('success')


class DepartmentRemoveHandler(BaseHandler):
    @tornado.web.authenticated
    def post(self):
        id = self.get_argument("id")
        department = self.db.query(models.Department).filter_by(id=id).one()
        self.db.delete(department)
        self.write('success')


class DepartmentAddHandler(BaseHandler):

    @tornado.web.authenticated
    def post(self):
        name = self.get_argument("name")
        person = self.get_argument("person")
        phone = self.get_argument("phone")
        mobile = self.get_argument("mobile")
        email = self.get_argument("email")
        department = models.Department(name=name,
                                       person=person,
                                       phone=phone,
                                       mobile=mobile,
                                       email=email)
        self.db.add(department)
        self.db.commit()
        self.write('success')

gcl = []


class GlobalSocketHandler(websocket.WebSocketHandler):

    def check_origin(self, origin):
        return True

    def open(self):
        if self not in gcl:
            gcl.append(self)

    def on_close(self):
        if self in gcl:
            gcl.remove(self)

cl = []


class SocketHandler(websocket.WebSocketHandler):

    def check_origin(self, origin):
        return True

    def open(self):
        if self not in cl:
            cl.append(self)

    def on_close(self):
        if self in cl:
            cl.remove(self)


class ApiHandler(BaseHandler):

    @tornado.web.asynchronous
    # @tornado.web.authenticated
    def get(self, *args):
        '''
        self.finish()
        location_id = self.get_argument("location_id")
        _type = self.get_argument("event_type")
        factor = self.get_argument("event_factor")
        snapshot = self.get_argument("snapshot")
        print snapshot
        dt = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        data = {"snapshot": snapshot, "factor": factor,
                "location_id": location_id, "type": _type, "dt": dt}
        data = json.dumps(data)
        for c in cl:
            c.write_message(data)
        '''
        pass

    @tornado.web.asynchronous
    def post(self):
        self.finish()
        raw_data = self.request.body
        res = json.loads(raw_data)
        location_id = res['location_id']
        _type = res['event_type']
        factor = res['event_factor']
        snapshot = res['snapshot']
        raw_dt = datetime.now()
        dt = raw_dt.strftime('%Y-%m-%d %H:%M:%S')
        data = {"snapshot": snapshot, "factor": factor,
                "location_id": location_id, "type": _type, "dt": dt}
        data = json.dumps(data)
        for c in cl:
            c.write_message(data)
        snapshot_path = util.base64ToImage(snapshot, _type)
        event = models.Event(location_id=location_id,
                             type=_type,
                             factor=factor,
                             dt=raw_dt,
                             snapshot=snapshot_path,
                             status=0)
        self.db.add(event)
        self.db.commit()
        events = self.db.query(models.Event).all()
        print len(events)
        nb = {'num_event': len(events)}
        print nb
        nb = json.dumps(nb)
        for gc in gcl:
            gc.write_message(nb)


def main():
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    print "Engine start at", options.port
    tornado.ioloop.IOLoop.instance().start()

if __name__ == '__main__':
    main()
