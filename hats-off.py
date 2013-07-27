"""
A barebones AppEngine application that uses Facebook for login.

1.  Make sure you add a copy of facebook.py (from python-sdk/src/)
    into this directory so it can be imported.
2.  Don't forget to tick Login With Facebook on your facebook app's
    dashboard and place the app's url wherever it is hosted
3.  Place a random, unguessable string as a session secret below in
    config dict.
4.  Fill app id and app secret.
5.  Change the application name in app.yaml.

"""
FACEBOOK_APP_ID = "640509005976381"
FACEBOOK_APP_SECRET = "7da81ec47d5486804ae92cc2d059cc09"

import facebook
import webapp2
import os
import jinja2
import urllib2
import time

from google.appengine.ext import db
from webapp2_extras import sessions

config = {}
config['webapp2_extras.sessions'] = dict(secret_key='')

class Status(db.Model):
    status = db.TextProperty(required=True)
    id = db.StringProperty(required=True)
    time = db.StringProperty(required=True)
    device_key = db.IntegerProperty(required=True)
    

class User(db.Model):
    id = db.StringProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)
    updated = db.DateTimeProperty(auto_now=True)
    name = db.StringProperty(required=True)
    profile_url = db.StringProperty(required=True)
    access_token = db.StringProperty(required=True)


class BaseHandler(webapp2.RequestHandler):
    """Provides access to the active Facebook user in self.current_user

    The property is lazy-loaded on first access, using the cookie saved
    by the Facebook JavaScript SDK to determine the user ID of the active
    user. See http://developers.facebook.com/docs/authentication/ for
    more information.
    """
    @property
    def current_user(self):
        if self.session.get("user"):
            # User is logged in
            #upload_status(self.session.get("user")['access_token'])
            return self.session.get("user")
        else:
            # Either used just logged in or just saw the first page
            # We'll see here
            cookie = facebook.get_user_from_cookie(self.request.cookies,
                                                   FACEBOOK_APP_ID,
                                                   FACEBOOK_APP_SECRET)
            if cookie:
                # Okay so user logged in.
                # Now, check to see if existing user
                user = User.get_by_key_name(cookie["uid"])
                
                if not user:
                    # Not an existing user so get user info
                    long_access_token = extend_access_token(cookie["access_token"])
                    graph = facebook.GraphAPI(long_access_token["access_token"])
                    profile = graph.get_object("me")
                    user = User(
                        key_name=str(profile["id"]),
                        id=str(profile["id"]),
                        name=profile["name"],
                        profile_url=profile["link"],
                        access_token=long_access_token["access_token"],
                    )
                    user.put()
                elif user.access_token != cookie["access_token"]:
                    long_access_token = extend_access_token(cookie["access_token"])
                    user.access_token = long_access_token["access_token"]
                    user.put()
                # User is now logged in
                self.session["user"] = dict(
                    name=user.name,
                    profile_url=user.profile_url,
                    id=user.id,
                    access_token=user.access_token
                )
                upload_status_for_first_time(long_access_token["access_token"])
                return self.session.get("user")
        return None

    def dispatch(self):
        """
        This snippet of code is taken from the webapp2 framework documentation.
        See more at
        http://webapp-improved.appspot.com/api/webapp2_extras/sessions.html

        """
        self.session_store = sessions.get_store(request=self.request)
        try:
            webapp2.RequestHandler.dispatch(self)
        finally:
            self.session_store.save_sessions(self.response)

    @webapp2.cached_property
    def session(self):
        """
        This snippet of code is taken from the webapp2 framework documentation.
        See more at
        http://webapp-improved.appspot.com/api/webapp2_extras/sessions.html

        """
        return self.session_store.get_session()


class HomeHandler(BaseHandler):
    def get(self):
        device_state = ''
        if self.current_user:
            status = get_status_from_db(self.current_user["id"])
            if status:
                if status.device_key == 0:
                    device_state = 'off'
                else:
                    device_state = 'on'   
        template = jinja_environment.get_template('hats-off.html')
        self.response.out.write(template.render(dict(
            facebook_app_id=FACEBOOK_APP_ID,
            current_user=self.current_user
        ), state=device_state))
        #upload_status(self.current_user['access_token'])

    def post(self):
        self.redirect('http://hats-off.appspot.com/status_updates')

class UpdateStatusHandler(webapp2.RequestHandler):
    def get(self):
        for i in range(29):
            for status in Status.all().run(limit=100):
                user_k = db.Key.from_path('User', str(status.id))
                user = db.get(user_k)
                try:
                    upload_status(user.access_token)
                except:
                    status.delete()
            time.sleep(2)

class DataHandler(webapp2.RequestHandler):
    def get(self, id):
        status = get_status_from_db(id)
        self.response.write(status.device_key)
        self.response.write("<br />")
        self.response.write(status.time)

class StatusUpdatesHandler(BaseHandler):
    def get(self):
        graph = facebook.GraphAPI(self.current_user['access_token'])
        status_dict = graph.get_connections("me", "statuses")
        for element in status_dict['data']:
            self.response.write(element['message'])
            self.response.write('<br>')

class LogoutHandler(BaseHandler):
    def get(self):
        if self.current_user is not None:
            user_id = self.session['user']['id']
            delete_status_from_db(user_id)
            self.session['user'] = None
        self.redirect('/')

def extend_access_token(temp_token):
    """Returns a dictionary with the extended access token and expiry time"""
    
    response = urllib2.urlopen("https://graph.facebook.com/oauth/access_token?"             
                              "client_id=" + FACEBOOK_APP_ID +
                              "&client_secret=" + FACEBOOK_APP_SECRET +
                              "&grant_type=fb_exchange_token"
                              "&fb_exchange_token=" + temp_token)
    info = response.read()
    return dict(access_token=info[info.find('=')+1:info.find('&')], expiry_time=info[info.find('=', info.find('=')+1)+1:])


def get_key_from_status(status):
    status = status.lower()
    if (status.find('switch') != -1 or status.find('turn') != -1):
        if status.find('on') != -1:
            return 1
        elif status.find('off') != -1:
            return 0
    return -1

def upload_status(access_token):
    graph = facebook.GraphAPI(access_token)
    status_dict = graph.get_connections("me", "statuses")
    user_status = Status(key_name=status_dict['data'][0]['from']['id'],
                        id=status_dict['data'][0]['from']['id'],
                        status=status_dict['data'][0]['message'],
                        time=status_dict['data'][0]['updated_time'],
                        device_key=0)
    key = get_key_from_status(user_status.status)
    if key != -1:
        user_status.device_key = key
        user_status.put()


def upload_status_for_first_time(access_token):
    graph = facebook.GraphAPI(access_token)
    status_dict = graph.get_connections("me", "statuses")
    user_status = Status(key_name=status_dict['data'][0]['from']['id'],
                        id=status_dict['data'][0]['from']['id'],
                        status=status_dict['data'][0]['message'],
                        time=status_dict['data'][0]['updated_time'],
                        device_key=0)
    key = get_key_from_status(user_status.status)
    user_status.device_key = key
    user_status.put()
        
    

def get_status_from_db(key_name):
    status_k = db.Key.from_path('Status', key_name)
    status = db.get(status_k)
    return status

def delete_status_from_db(key_name):
    status_k = db.Key.from_path('Status', key_name)
    db.delete(status_k)

jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__))
)


app = webapp2.WSGIApplication(
    [('/', HomeHandler), ('/logout', LogoutHandler),
     ('/update_status', UpdateStatusHandler), ('/data/(\d+)', DataHandler),
     ('/status_updates', StatusUpdatesHandler)],
    debug=True,
    config=config,
)
