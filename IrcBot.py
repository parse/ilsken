import socket, re
from SpotifyMetaData import Metadata #Import Spotimeta (http://pypi.python.org/pypi/spotimeta/0.2)

# @todo: Multiple networks

class IrcBot:    
    network = ''
    port = 0
    nick = ''
    channel = []
    irc = None
    
    def __init__ (self, params):
        """Init bot using served parameters"""
        
        self.network = params['server']
        self.port = params['port']
        self.nick = params['nick']
        self.channel = params['channel']
        
    def connect(self):
        """Connect bot to network and keep the connection going"""
        
        self.irc = socket.socket (socket.AF_INET, socket.SOCK_STREAM)
        self.irc.connect ((self.network, self.port))
        
        self.__log( self.irc.recv (4096) )
        
        self.__sysMsg ('NICK ' + self.nick)
        self.__sysMsg ('USER ' + self.nick + ' ' + self.nick + ' ' + self.nick + ' :Python IRC')
        
        for chanItem in self.channel:
            self.__sysMsg ('JOIN ' + chanItem)
        
        while True:
            data = self.irc.recv (4096)
            dataSplit = data.split(' ');
            
            if len(dataSplit) <= 3 :
                if data.find ('PING') != -1:
                    self.__sysMsg ('PONG ' + data.split() [ 1 ])
                    self.__log('PONG ' + data.split() [ 1 ])
            else:       
                if data.find('PRIVMSG') != -1:
                    self.__handleData(data)
                else:
                    self.__log(data)

    def __parseData(self, msg):
        """Generate a dictionary for msg, channel and sender"""
        
        complete = msg[1:].split(':',1) 
        info = complete[0].split(' ')
        sender = info[0].split('!')

        return { 'channel' : info[2], 'sender' : sender[0], 'msg' : '' . join(complete[1]) }
        
    def __handleData(self, data):
        """Parse user submitted data and handle it appropriate"""
        
        self.__log(data)
        dataInfo = self.__parseData(data)
        
        # Add Spotify-functionality
        self.__handleSpotify(dataInfo)
        self.__handleYoutube(dataInfo)
        
    def __handleYoutube(self, dataInfo):
        """Identify Youtube-tracks and albums and take result from MetaData-api"""
        
        #youPattern = re.compile('youtube\.com\/watch\?v=([A-Za-z0-9._%-]*)[&\w;=\+_\-]')
        youPattern = re.compile('http:\/\/([a-z]+\.)?youtube.com\/watch\?v=([A-Za-z0-9._%-]+)')
        youBark = youPattern.search( dataInfo['msg'] )
        
        if youBark:
            try:
                youGroups = youBark.groups()
                import urllib2
                from BeautifulSoup import BeautifulSoup
                
                url = "http://www.youtube.com/watch?v=%s" % youGroups[1]
                f = urllib2.urlopen(url)

                soup = BeautifulSoup( f.read() )
                title = soup.html.head.title.string
                
                replaceList = [('\n', '')]
                for search, replace in replaceList:
                    title = title.replace(search, replace)

                r = title.lstrip()
            except:
                r = "(Error fetching video)"
                
            self.__privMsg(dataInfo['channel'], dataInfo['sender'] + ': ' + r)
                 
    def __handleSpotify(self, dataInfo):
        """Identify Spotify-tracks and albums and take result from MetaData-api"""
        
        spotPattern = re.compile('spotify:(.*?):(.*?)\s')
        spotBark = spotPattern.search( dataInfo['msg'])
        
        if spotBark:
            try:
                spotGroups = spotBark.groups()
                                
                # Init Metadata-lib
                metacache = {}
                metadata = Metadata(cache=metacache)
                metaInfo = metadata.lookup('spotify:'+spotGroups[0]+":"+spotGroups[1])
                
                if spotGroups[0] == 'track' or spotGroups[0] == 'album':
                    r = metaInfo["result"]["artist"]["name"] + ' - ' + metaInfo["result"]["name"]
                else:
                    r = '(Not found)'
            except:
                # @todo: Fetch RateLimiting instead of doing a "casual case" like this
                r = "(Limit exceeded or wrong input)"
                
            self.__privMsg(dataInfo['channel'], dataInfo['sender'] + ': ' + r)
            
    def __log(self, msg):
        """Log to command line with a following linebreak"""
        
        print msg + '\n'
        
    def __sysMsg(self, cmd):
        """Send commands to server with appropriate \r\n"""
        
        self.irc.send(cmd + '\r\n')
        
    def __privMsg(self, target, msg):
        """Send privMsg to target (user or channel)"""
        
        msg = 'PRIVMSG ' + target + ' :' + msg
        
        self.__sysMsg ( msg )
        self.__log(msg)
        
params = {
    'server' : 'irc.freenode.net', \
    'port' : 6667, \
    'nick' : 'ilsken2', \
    'channel' : ['#asdfasdf'] \
        }

bot = IrcBot(params)
bot.connect()