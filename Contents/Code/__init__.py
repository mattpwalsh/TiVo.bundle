from time import sleep, time
from subprocess import *
import os
from signal import *
import urllib2, cookielib, os.path
from lxml import etree
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from SocketServer import ThreadingMixIn
import base64
import string
import socket
import thread
import pybonjour
import select
import re
import sys
import ctypes
try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty
    
ON_POSIX = 'posix' in sys.builtin_module_names

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    pass



TIVO_CONTENT_FOLDER     = "x-tivo-container/folder"
TIVO_CONTENT_SHOW_TTS   = "video/x-tivo-raw-tts"
TIVO_CONTENT_SHOW_PES   = "video/x-tivo-raw-pes"

TIVO_PLUGIN_PREFIX   = "/video/tivo"
TIVO_BY_NAME         = "tivo-name"
TIVO_BY_IP_SHOW      = "tivo-ip-show"
TIVO_GET_SHOW        = "tivo-fetch"
TIVO_PREFS           = "prefs"

TIVO_PORT            = 49492

TIVO_XML_NAMESPACE   = 'http://www.tivo.com/developer/calypso-protocol-1.6/'
TIVO_SITE_URL        = "http://"
TIVO_LIST_PATH       = "/TiVoConnect?Command=QueryContainer&Recurse=No&Container=%2FNowPlaying"

CookiesFile = "/cookies"
CookiesJar  = cookielib.LWPCookieJar()

####################################################################################################

def Start():
  Plugin.AddPrefixHandler(TIVO_PLUGIN_PREFIX, getTivoNames, "TiVo", "icon-default.jpg", "art-default.jpg")
  Plugin.AddViewGroup("InfoList", viewMode="InfoList", mediaType="items")  
  
  tvd = Resource.ExternalPath("tivodecode")
  if Platform.OS == 'Windows':
        tvd = Resource.ExternalPath("tivodecode.exe")
  Log.Debug(tvd)
  #os.chmod(tvd, 0755)
  Thread.Create(findTivos)
  Thread.Create(TivoServerThread, ip=Network.Address, port=TIVO_PORT)

####################################################################################################
  
def getTivoNames():
    dir = MediaContainer(R('art-default.jpg'), title1="TiVo")

    myMAK = Prefs["MAK"]
    if myMAK == None:
      myMAK = ""
    if (len(myMAK) == 10):
        tivo_list = Dict['tivos']
        Log.Debug(tivo_list)
        for tivo in tivo_list:
            dir.Append(Function(DirectoryItem(getTivoShows, tivo), tivoName = tivo))


    dir.Append(PrefsItem("Preferences"))
    dir.Append(Function(DirectoryItem(findTivosFromMenu, "Find Tivos")))
    return dir

####################################################################################################

def TivoPrefs(count, pathNouns):
  if (count == 3):
    Prefs.Set(pathNouns[1], pathNouns[2])
    return getTivoNames()
  else:
    return getTivoNames()

####################################################################################################

def getTivoShows(sender,tivoName):
  Log.Debug(tivoName)
  dir = MediaContainer(R('art-default.jpg'), title1="TiVo", title2=tivoName)

  hostname = Dict['tivos'][tivoName]['hosttarget']
  tivoip = Dict['tivos'][tivoName]['ip']
  url = "https://" + tivoip + ":443" + TIVO_LIST_PATH
  return getTivoShowsByIPURL(tivoip, url, dir, 1)

####################################################################################################

def getTivoEpisodes(sender, tivoip, show_id, showname):
  dir = MediaContainer(R('art-default.jpg'), title1="TiVo", title2=showname)
  url = "https://" + tivoip + ":443" + TIVO_LIST_PATH + "%2F" + show_id
  if showname == "HD Recordings" or showname == "TiVo Suggestions":
    return getTivoShowsByIPURL(tivoip, url, dir, 1)
  else:
    return getTivoShowsByIPURL(tivoip, url, dir, 0)

####################################################################################################

def getTivoShowsByIPURL(tivoip, url, dir, expand_name):
  
  dir.viewGroup ="InfoList"
  try:
    authhandler = urllib2.HTTPDigestAuthHandler()
    authhandler.add_password("TiVo DVR", "https://" + tivoip + ":443/", "tivo", Prefs["MAK"])
    opener = urllib2.build_opener(authhandler)
    pagehandle = opener.open(url)
  except IOError, e:
    Log.Debug("Got a URLError trying to open %s" % url)
    if hasattr(e, 'code'):
      Log.Debug("Failed with code : %s" % e.code)
      if (int(e.code) == 401):
        dir = MessageContainer("Couldn't authenticate", "Failed to authenticate to tivo.  Is the Media Access Key correct?")
      else:
        dir = MessageContainer("Couldn't connect", "Failed to connect to tivo")
    if hasattr(e, 'reason'):
      Log.Debug("Failed with reason : %s" % e.reason)
    return dir
  except:
    Log.Debug ("Unexpected error trying to open %s" % url)
    return

  myetree = etree.parse(pagehandle).getroot()

  for show in myetree.xpath("g:Item", namespaces={'g': TIVO_XML_NAMESPACE}):
    show_name = getNameFromXML(show, "g:Details/g:Title/text()")
    show_content_type = getNameFromXML(show, "g:Details/g:ContentType/text()")
    if (show_content_type == TIVO_CONTENT_FOLDER):
      show_total_items = int(getNameFromXML(show, "g:Details/g:TotalItems/text()"))
      show_folder_url = getNameFromXML(show, "g:Links/g:Content/g:Url/text()")
      show_folder_id = show_folder_url[show_folder_url.rfind("%2F")+3:]
      item = Function(DirectoryItem(getTivoEpisodes, title="[" + show_name + "]", thumb=R("art-default.jpg")), tivoip=tivoip, show_id=show_folder_id, showname=show_name)
      dir.Append(item)

    elif ((show_content_type == TIVO_CONTENT_SHOW_TTS) or
          (show_content_type == TIVO_CONTENT_SHOW_PES)) :
      show_duration = getNameFromXML(show, "g:Details/g:Duration/text()")
      show_episode_name = getNameFromXML(show,"g:Details/g:EpisodeTitle/text()")
      show_episode_num = getNameFromXML(show, "g:Details/g:EpisodeNumber/text()")
      show_desc = getNameFromXML(show, "g:Details/g:Description/text()")
      show_url = getNameFromXML(show, "g:Links/g:Content/g:Url/text()")
      show_in_progress = getNameFromXML(show,"g:Details/g:InProgress/text()")
      show_copyright = getNameFromXML(show, "g:Details/g:CopyProtected/text()")
      
      show_desc = show_desc[:show_desc.rfind("Copyright Tribune Media")]
      show_id  =  show_url[show_url.rfind("&id=")+4:]
      if (show_episode_num != ""):
        show_season_num = show_episode_num[:-2]
        show_season_ep_num = show_episode_num[-2:]

      if (show_episode_name != ""):
        extra_name = show_episode_name
      elif (show_episode_num != ""):
        extra_name = show_episode_num
      else:
        extra_name = show_id
      if (expand_name == 1):
        target_name = show_name + " : " + extra_name
      else:
        target_name = extra_name
      if show_copyright != "Yes" and show_in_progress != "Yes":
        
        url = "http://"+Network.Address+":" + str(TIVO_PORT) + "/" + tivoip + "/" + base64.b64encode(show_url, "_;")    
        #itempath = TIVO_PLUGIN_PREFIX + "/" +TIVO_GET_SHOW +"/" + tivoip +"/" + base64.b64encode(show_url, "_;") + "/" + base64.b64encode(show_name+" : "+extra_name, "_;")
        item = VideoItem(url,  title=target_name, summary=show_desc, duration=show_duration,thumb=R("art-default.jpg")) 
        if (show_episode_num != ""):
          subtitle = "Season " + show_season_num + "      Episode " + show_season_ep_num
          item.subtitle = subtitle
        dir.Append(item)

    else:
      Log.Debug("Found a different content type: " + show_content_type)

  return dir


####################################################################################################

def getNameFromXML(show, name, default=""):
   result = show.xpath(name, namespaces={'g': TIVO_XML_NAMESPACE})
   if (len(result) > 0):
     return result[0]
   else:
     return default

####################################################################################################

class MyVideoHandler(BaseHTTPRequestHandler):

  def do_HEAD(self):
    try:
      self.send_response(200)
      self.send_header('Content-Type', 'video/mpeg2')
      self.send_header('Accept-Ranges', 'none')
      self.end_headers()
      return
    except:
      Log.Debug("Got an Error")

  def do_GET(self):
    ip = string.split(self.path[1:], "/")[0]
    url = base64.b64decode(string.split(self.path[1:], "/", 1)[1], "_;")
    try:
      self.send_response(200)
      self.send_header('Content-type', 'video/mpeg2')
      self.send_header('Accept-Ranges', 'none')
      self.end_headers()
      
      q = Queue()
      
      #This is the subprocess to decode the tivo stream
      tivodecode = Helper.Process("tivodecode", "-m", Prefs["MAK"], "-")
      #This thread fetches from the tivo and writes it to the queue.
      tf = Thread.Create(tivoFetcher, True,url, q, tivodecode)
      
      #This thread reads the data from the queue, then sends it to tivodecode
      td = Thread.Create(tivoDecoder, True, q, tivodecode)
      
      CHUNK = 4192
      status = 0
      starttime = time()
      
      #Read the data from tivodecode and output it to the client
      while True:
          data = tivodecode.stdout.read(CHUNK)
          #if (CHUNK < (16 * 1024 * 1024)):
          #  CHUNK = CHUNK * 2
          #status += CHUNK
          #currenttime = time()
          #if ((currenttime-starttime) !=0):
          #  Log.Debug(((status/(1024*1024))*8)/(currenttime-starttime)) 
          if not data:             
                break
          self.wfile.write(data)
 

    except IOError, e:
      Log.Debug("Got an IO Error")
      Log.Debug(e)
      if hasattr(e, 'code'):
        Log.Debug("Failed with code : %s" % e.code)
      if hasattr(e, 'reason'):
        Log.Debug("Failed with reason :" + e.reason)
    except:
      Log.Debug ("Unexpected error : " + sys.exc_info())

    try:
      if Platform.OS == "Windows":
         Log.Debug("Attmpling to kill tvd:")
         Log.Debug(tivodecode.pid)
         if not winKill(tivodecode.pid): 
          Log.Debug("Couldn't kill")
      else:
        kill(tivodecode.pid, SIGTERM)
    except:
      Log.Debug("Self-exit of tivodecode")

    return

  def do_POST(self):
    Log.Debug("Got a Post")
  
  def handle_error(self, request, client_address):
    Log.Debug("Got an error..")
    

###########################################################3        
            
def tivoFetcher (url, q, tvd ):
      authhandler = urllib2.HTTPDigestAuthHandler()
      authhandler.add_password("TiVo DVR", url, "tivo", Prefs["MAK"])
      Log.Debug("Starting httpstuff1")
      opener= urllib2.build_opener(authhandler, urllib2.HTTPCookieProcessor(CookiesJar))
      Log.Debug("Starting httpstuff2 : " + url)      
      req = opener.open(url)
      CHUNK = 1 * 1024 * 1024
      status = 0
      starttime = time()
      while True and tvd.poll() !=0:
        Log.Debug("reading from tivo....")
        #Code to increment chunk size.  In theory, give the client some data to start dispalying asap, and then ramp up speeds to keep up with stream.
        #if (CHUNK < (4 * 1024 * 1024)):
        #    CHUNK = CHUNK * 2
        data = req.read(CHUNK)
        #Code to report mbps for each loop (assuming I got the math right)
        #status += CHUNK
        #currenttime = time()
        #if ((currenttime-starttime) !=0):
        #    Log.Debug(((status/(1024*1024))*8)/(currenttime-starttime))        
        #Log.Debug("read from tivo....")
        if not data: break
        #Log.Debug("writing to tvd...")
        try:
          q.put(data)
        except:
          Log.Debug("cannot add to queue")
          break
        
      Log.Debug("done fetching")
      
        
#################################################################

def tivoDecoder (q, tvd):
    while True and tvd.poll() != 0:
        data = q.get()
        try:
            tvd.stdin.write(data)
        except:
            Log.Debug("tvd already closed")
    try:
        tvd.stdin.close()
    except:
        Log.Debug("tvd already closed")
    

            
#################################################################        
def winKill(pid):
    """kill function for Win32"""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(1, 0, pid)
    return (0 != kernel32.TerminateProcess(handle, 0))
    
####################################################################################################

def TivoServerThread(ip, port):
  
  try:
    httpserver = HTTPServer((ip, port), MyVideoHandler)
    httpserver.serve_forever()
  except :
    Log.Debug("Server Already Running")
  
####################################################################################################

def findTivosFromMenu(sender):
    Thread.Create(findTivos)
    mc = MessageContainer("Finding Tivos","Please wait while the Tivos are discovered.   You may need to exit the tivo plugin to display any newly discovered tivos.")
    return mc



def findTivos():
    regtype  = '_tivo-videos._tcp'
    timeout  = 7
    queried  = []
    resolved = []
    Dict['tivos'] = {}
    current_tivo = {}

    def query_record_callback(sdRef, flags, interfaceIndex, errorCode, fullname,
                              rrtype, rrclass, rdata, ttl):
        if errorCode == pybonjour.kDNSServiceErr_NoError:
            tivo_list = Dict['tivos']
            for tivo in tivo_list:
                if tivo_list[tivo]['hosttarget'] == fullname:
                    Log.Debug("Queried: "+tivo)
                    tivo_list[tivo]['ip'] = socket.inet_ntoa(rdata)
            queried.append(True)


    def resolve_callback(sdRef, flags, interfaceIndex, errorCode, fullname, hosttarget, port, txtRecord):
        if errorCode != pybonjour.kDNSServiceErr_NoError:
            return
        shortName = fullname.replace('._tivo-videos._tcp.local.','').replace("\\032"," ")
        Log.Debug("Resolved: "+shortName)
        Dict['tivos'][shortName] = {'interfaceIndex': interfaceIndex,'port': port,'fullname': fullname,'hosttarget': hosttarget}
        query_sdRef = pybonjour.DNSServiceQueryRecord(interfaceIndex = interfaceIndex,
                                            fullname = hosttarget,
                                            rrtype = pybonjour.kDNSServiceType_A,
                                            callBack = query_record_callback)

        try:
            while not queried:
                ready = select.select([query_sdRef], [], [], timeout)
                if query_sdRef not in ready[0]:                    
                    break
                pybonjour.DNSServiceProcessResult(query_sdRef)
            else:
                queried.pop()
        finally:
            query_sdRef.close()

        resolved.append(True)


    def browse_callback(sdRef, flags, interfaceIndex, errorCode, serviceName,
                        regtype, replyDomain):
        if errorCode != pybonjour.kDNSServiceErr_NoError:
            return

        if not (flags & pybonjour.kDNSServiceFlagsAdd):
            return
        Log.Debug("Browsed: "+serviceName)
        Dict['tivos'][serviceName] = {}
        
    
        resolve_sdRef = pybonjour.DNSServiceResolve(0,
                                                    interfaceIndex,
                                                    serviceName,
                                                    regtype,
                                                    replyDomain,
                                                    resolve_callback)

        try:
            while not resolved:
                ready = select.select([resolve_sdRef], [], [], timeout)
                if resolve_sdRef not in ready[0]:
                    Log.Debug('Resolve timed out')
                    break
                pybonjour.DNSServiceProcessResult(resolve_sdRef)
            else:
                resolved.pop()
        finally:
            resolve_sdRef.close()


    browse_sdRef = pybonjour.DNSServiceBrowse(regtype = regtype,
                                              callBack = browse_callback)
    
    starttime = time()
    try:
        try:
            while True and (time() - starttime) < 10:
                ready = select.select([browse_sdRef], [], [], 1)
                if browse_sdRef in ready[0]:
                    pybonjour.DNSServiceProcessResult(browse_sdRef)
        except KeyboardInterrupt:
            pass
    finally:
        browse_sdRef.close()
      
        

        

        

