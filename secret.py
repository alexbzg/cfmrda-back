#!/usr/bin/python3
#coding=utf-8

import os, base64

def secret( fp ):
    secret = None
    if ( os.path.isfile( fp ) ):
        with open( fp, 'rb' ) as fSecret:
            secret = fSecret.read()
    if not secret:
        secret = base64.b64encode( os.urandom( 64 ) )
        with open( fp, 'wb' ) as fSecret:
            fSecret.write( str( secret ) )

