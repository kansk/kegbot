import BaseHTTPServer
import cgi
import simplejson
import socket
import logging
import time
import urllib2

from pykeg.core import Interfaces
from pykeg.core import kb_threads
from pykeg.core import models

class KegbotJsonRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
  def __init__(self, request, client_address, server):
    self._server = server
    self._handlers = {
      '/' : self.HandleRoot,
      '/Login' : self.HandleLogin,
      '/Logout': self.HandleLogout,
      '/CurrentFlow': self.HandleCurrentFlow,
    }
    BaseHTTPServer.BaseHTTPRequestHandler.__init__(self, request, client_address, server)

  def log_request(self, code=None, size=None):
    pass

  def do_GET(self):
    qpos = self.path.find('?')
    self.body = {}
    if qpos >= 0:
      self.body = cgi.parse_qs(self.path[qpos+1:], keep_blank_values=1)
      self.path = self.path[:qpos]
    handler = self._handlers.get(self.path, self.HandleDefault)
    return handler()

  def _DoResponse(self, body, code=200, type="text/plain"):
    self.send_response(200)
    self.send_header("Content-type", type)
    self.end_headers()
    try:
      self.wfile.write(body)
    except:
      pass

  def HandleRoot(self):
    data = open('/var/www/localhost/htdocs/kjax/index.html').read()
    self._DoResponse(data, type="text/html")

  def HandleDefault(self):
    self._DoResponse('Not implemented', 503)

  def HandleLogin(self, log_in=True):
    username = self.body.get('username')
    if not username:
      self._DoResponse('no username', 500)
    else:
      self._server.AuthUser(username[0], log_in)
      self._DoResponse('ok')

  def HandleLogout(self):
    self._server.ClearAuthed()
    self._DoResponse('ok')

  def _GetFlowDict(self):
    flow = self._server.CurrentFlow()
    if not flow:
      return {}
    #q = models.UserPicture.objects.filter(user=flow.user.id)
    # TODO FIXME
    img_url = 'http://sfo.kegbot.org/site_media/images/unknown-drinker.png'
    #if len(q):
    #  pic = q[0]
    #  img_url = 'media/' + pic.image.url

    ret = {
      'channel': 0,
      'user': flow.user.username,
      'img_url': img_url,
      'volume_oz': flow.Volume().ConvertTo.Ounce,
    }
    return ret

  def HandleCurrentFlow(self):
    flow = self._GetFlowDict()
    self._DoResponse(simplejson.dumps(flow))


class KegbotJsonServer(kb_threads.KegbotThread, BaseHTTPServer.HTTPServer,
  Interfaces.IAuthDevice, Interfaces.IFlowListener):
  def __init__(self, addr):
    kb_threads.KegbotThread.__init__(self, 'jsonservice')
    BaseHTTPServer.HTTPServer.__init__(self, addr, KegbotJsonRequestHandler)
    self._addr = addr
    self._current_flow = None
    self._last_drinks = []
    self._authed = set()
    self._logger = logging.getLogger('jsonserver')

  def run(self):
    self._logger.info("server started")
    while not self._quit:
      self.handle_request()
    self.server_close()
    self._logger.info("server closed")

  def Quit(self):
    kb_threads.KegbotThread.Quit(self)
    if self.isAlive():
      # The main loop is blocking on handle_request; push a bogus request through
      # to unblock.
      host, port = self._addr
      quit_url = 'http://localhost:%i/quit' % port
      self._logger.info('sending quit request')
      urlfp = urllib2.urlopen(quit_url)
      urlfp.read()
      urlfp.close()
      del urlfp

  def CurrentFlow(self):
    return self._current_flow

  def LastDrinks(self):
    return self._last_drinks

  def ClearAuthed(self):
    self._authed.clear()

  def AuthUser(self, username, log_in=True):
    if log_in:
      self._authed.clear()
      self._authed.add(username)
    else:
      try:
        self._authed.remove(username)
      except KeyError:
        pass

  ### IAuthDevice
  def AuthorizedUsers(self):
    return self._authed

  ### IFlowListener interface
  def FlowStart(self, flow):
    self._current_flow = flow

  def FlowUpdate(self, flow):
    self._current_flow = flow

  def FlowEnd(self, flow, drink):
    self._current_flow = None