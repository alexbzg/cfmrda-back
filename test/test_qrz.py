#!/usr/bin/python3
#coding=utf-8
import logging, unittest, asyncio

from cfmrda.qrz import QRZComLink

logging.basicConfig( level = logging.DEBUG,
        format='%(asctime)s %(message)s', 
        datefmt='%Y-%m-%d %H:%M:%S' )
logging.info( 'starting qrz tests' )


class TestQrz(unittest.TestCase):

    def setUp( self ):
        logging.info( 'create qrz.com link' )
        self.qcl = QRZComLink( asyncio.get_event_loop() )

    def testGetData( self ):
        logging.info( 'test qrz.com query' )
        data = self.qcl.getData( 'R7CL' )
        self.assertEqual( data['email'], 'welcome@masterslav.ru' )

if __name__ == '__main__':
    unittest.main()

