#!/usr/bin/python3
#coding=utf-8

import asyncio, logging, unittest, requests, json, jwt, os, time

logging.basicConfig( level = logging.DEBUG,
        format='%(asctime)s %(message)s', 
        datefmt='%Y-%m-%d %H:%M:%S' )
logging.info( 'starting server tests' )

srvURL = 'http://dev.cfmrda.ru/aiohttp'

class TestSrv(unittest.TestCase):

    def testGet( self ):
        r = requests.get( srvURL + '/test' )
        self.assertEqual( r.status_code, requests.codes.ok )
        self.assertEqual( r.text, 'OK' )
        r.connection.close()


#    def testLogQSO( self ):
#        r = requests.post( srvURL + '/log', \
#            data = json.dumps( { 'qso': 'blahblahblah', 'token': token } ) )
#        self.assertEqual( r.status_code, requests.codes.ok )
#        print( r.text )
#        r.connection.close()

#    def testChangePasswordEmail( self ):
#        r = requests.post( srvURL + '/userSettings', \
#            data = json.dumps( { 'token': token, 'email': '18@73.ru', 'password': '222222' } ) )
#        self.assertEqual( r.status_code, requests.codes.ok )
#        print( r.text )
#        r.connection.close()

#    def testChangePasswordWToken( self ):
#        if not secret:
#            print( 'Test skipped - no secret' )
#        timeToken = jwt.encode( 
#            { 'callsign': 'qqqq', 'time': time.time() }, \
#            secret, algorithm='HS256' ).decode('utf-8')
#        r = requests.post( srvURL + '/userSettings', \
#            data = json.dumps( { 'token': timeToken, 'password': '111111' } ) )
#        self.assertEqual( r.status_code, requests.codes.ok )
#        print( r.text )
#        r.connection.close()


if __name__ == '__main__':
    unittest.main()

