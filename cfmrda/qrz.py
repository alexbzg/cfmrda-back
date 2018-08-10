#!/usr/bin/python3
#coding=utf-8

from cfmrda.common import siteConf
import requests, json, os, logging, xmltodict

class QRZComLink:

    def __init__( self, loop ):
        conf = siteConf()
        self.loop = loop
        self.login = conf.get( 'QRZCom', 'login' )
        self.password = conf.get( 'QRZCom', 'password' )
        self.sessionID = None
        self.getSessionID()

    def getSessionID( self ):
        conf = siteConf()
        fpSession = conf.get( 'QRZCom', 'session_file' )
        if ( os.path.isfile( fpSession ) ):
            with open( fpSession, 'r' ) as fSession:
                sessionID = fSession.read()
                if self.sessionID != sessionID:
                    self.sessionID = sessionID
                    return

        r, rBody = None, None
        try:
            r = requests.get( 'http://xmldata.qrz.com/xml/current/?username=' \
                    + self.login + ';password=' + self.password )
            rBody = r.text
            r.raise_for_status()
            rDict = xmltodict.parse( rBody )
            if 'Key' in rDict['QRZDatabase']['Session']:
                self.sessionID = rDict['QRZDatabase']['Session']['Key']
                with open( fpSession, 'w' ) as fSession:
                    fSession.write( self.sessionID )
            else:
                raise Exception( 'Wrong QRZ response' )
        except Exception as e:
            logging.exception( 'Error logging into QRZ.com' )
            if r:
                logging.error( 'Http result code: ' + str( r.status_code() ) )
                logging.error( 'Http response body: ' + r )
            self.loop.call_later( 60*10, self.getSessionID )

    def getData( self, cs, bio = False ):
        if self.sessionID:
            r, rBody = None, None
            type = 'html' if bio else 'callsign'
            try:
                r = requests.get( 'http://xmldata.qrz.com/xml/current/?s=' \
                        + self.sessionID + ';' + type + '=' + cs )
                rBody = r.text
                r.raise_for_status()
                if bio:
                    return rBody
                rDict = xmltodict.parse( rBody )
                if 'Callsign' in rDict['QRZDatabase']:
                    return rDict['QRZDatabase']['Callsign']
                elif 'Session' in rDict['QRZDatabase'] and \
                    'Error' in rDict['QRZDatabase']['Session'] and \
                    ( rDict['QRZDatabase']['Session']['Error'] == \
                        'Session Timeout' or \
                        rDict['QRZDatabase']['Session']['Error'] == \
                        'Invalid session key' ) :
                        self.getSessionID()
                        if self.sessionID:
                            return self.getData( cs )
                elif 'Session' in rDict['QRZDatabase'] and \
                    'Error' in rDict['QRZDatabase']['Session']:
                        if 'Not found' in rDict['QRZDatabase']['Session']['Error']:
                            return None
                        else:
                            raise Exception( 'QRZ error: ' + \
                                rDict['QRZDatabase']['Session']['Error'] )
                else:
                    raise Exception( 'Wrong QRZ response: ' + json.dumps( rDict ) )
            except Exception as e:
                logging.exception( 'Error querying QRZ.com' )
                if r:
                    logging.error( 'Http result code: ' + str( r.status_code() ) )
                    logging.error( 'Http response body: ' + r )
                return None
        else:
            self.getSessionID()
            if self.sessionID:
                return self.getData( cs )

