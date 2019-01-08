#!/usr/bin/env python3
# coding=utf-8

import pychromecast
import requests
import threading
import argparse
import time
import os
import sys
import cherrypy
import urllib
import json
import socket
import traceback

# dummy stream handler object for cherrypy
class stream_handler(object):
    pass


def web_server():

    # engine config
    cherrypy.config.update({'environment': 'production',
                            'log.screen': False,
                            'log.access_file': '',
                            'log.error_file': ''})

    # Listen on our port on any IF
    cherrypy.server.socket_host = '0.0.0.0'
    cherrypy.server.socket_port = 8000

    # webhook for audio streaming
    # det up for directory serving
    web_conf = {
       '/': {
           'tools.staticdir.on': True,
           'tools.staticdir.dir': '/',
           'tools.staticdir.index': 'index.html',
       }
    }

    cherrypy.tree.mount(stream_handler(), '/', web_conf)

    # Cherrypy main loop blocking
    cherrypy.engine.start()
    cherrypy.engine.block()


def volumio_uri_to_url(server_ip,
                       uri):
    # Radio/external stream
    # uri will start with http
    if uri.startswith('http'):
        chromecast_url = uri
        type = "audio/mp3"
    else:
        # Format file URL as path from our web server
        chromecast_url = "http://%s:8000/%s" % (server_ip,
                                                uri)

        # Split out extension of file
        # probably not necessary as chromecast seems to work it
        # out itself
        file, ext = os.path.splitext(uri)
        type = "audio/%s" % (ext.replace('.', ''))

    return (chromecast_url, type)
    

def volumio_agent(host,
                  port,
                  server_ip):

    api_session = requests.session()

    cast_device = None # initial state

    ctrl_create_count = 0
    failed_status_update_count = 0

    # Cast state inits
    cast_status = 'none'
    cast_uri = 'none'
    cast_volume = 0
    cast_confirmed = 0
    
    while (1):
        # 1 sec delay per iteration
        time.sleep(1)

        # Get status from Volumio
        # Added exception protection to blanket 
        # cover a failed API call or any of th given fields 
        # not being found for whatever reason
        try:
            resp = api_session.get('http://localhost:3000/api/v1/getstate')
            json_resp = resp.json()
            status = json_resp['status']
            uri = json_resp['uri']
        except:
            continue

        volumio_status_str = json.dumps(json_resp, indent = 4)
        print("\n%s Volumio State:\n%s\n" % (
            time.asctime(),
            volumio_status_str))

        # switch 'music-library' to 'mnt' if present
        # Need this to represent absolute path of file
        uri = uri.replace('music-library', 'mnt')

        volume = int(json_resp['volume']) / 100 # scale to 0.0 to 1.0 for Chromecast

        # Controller management
        # Handles first creation of the controller and 
        # recreation of the controller after detection of stale connections
        # also only does this if we're in a play state
        if (status == 'play' and 
                cast_device is None):
            print("%s Connecting to Chromecast %s:%d" % (
                time.asctime(), 
                host, 
                port))
            cast_device = pychromecast.Chromecast(host, port)

            # Kill off any current app
            print("%s Waiting for device to get ready.." % (time.asctime()))
            if not cast_device.is_idle:
                print("Killing current running app")
                cast.quit_app()

            while not cast_device.is_idle:
                time.sleep(1)

            print("%s Connected to %s (%s) model:%s" % (
                time.asctime(), 
                cast_device.name,
                cast_device.uri,
                cast_device.model_name))

            ctrl_create_count += 1

            # Cast state inits
            cast_status = 'none'
            cast_uri = 'none'
            cast_volume = 0
            cast_confirmed = 0


        # Skip remainder of loop if we have no device to 
        # handle. This will happen if we are in an initial stopped or 
        # paused state or ended up in these states for a long period
        if (cast_device is None):
            print("%s No active Chromecast device" % (time.asctime()))
            continue

        # Detection of Events from Volumio
        # All of these next code blocks are trying to compare
        # some property against a known cast equivalent to determine 
        # a change has occured and action required

        # Volume change only while playing
        if (cast_volume != volume and
                cast_status == 'play'):

            print("Setting Chromecast Volume: %.2f" % (volume))
            cast_device.set_volume(volume)
            cast_volume = volume
    
        # Pause
        if (cast_status != 'pause' and
            status == 'pause'):

            print("Pausing Chromecast")
            cast_device.media_controller.pause()
            cast_status = status
        
        # Resume play
        if (cast_status == 'pause' and 
            status == 'play'):

            print("Unpause Chromecast")
            cast_device.media_controller.play()
            cast_status = status
        
        # Stop
        if (cast_status != 'stop' and 
            status == 'stop'):

            # This can be an actual stop or a 
            # switch to the next track
            # the uri field will tell us this

            if (uri == ''):
                # normal stop no next track set
                # We can also ditch the device
                print("Stop Chromecast")
                cast_device.media_controller.stop()
                cast_status = status
                cast_device = None

            elif (uri != cast_uri):
                # track switch
                chromecast_url, type = volumio_uri_to_url(server_ip, uri)
                print("Casting URL (paused):%s type:%s" % (
                    chromecast_url.encode('utf-8'),
                    type))

                # Prep for playback but paused
                # autoplay = False
                cast_device.play_media(chromecast_url, 
                                       content_type = type,
                                       autoplay = False)

                # Assume in paused state
                # Another 'play' event will trigger us 
                # out of this assumed paused state
                cast_status = 'pause'
                cast_uri = uri
                cast_confirmed = 0 

    

        # Play a song or stream or next in playlist
        if ((cast_status != 'play' and
            status == 'play') or
            (status == 'play' and uri != cast_uri)):

            chromecast_url, type = volumio_uri_to_url(server_ip, uri)
    
            print("Casting URL:%s type:%s" % (
                chromecast_url.encode('utf-8'),
                type))

            # Let the magic happen
            cast_device.play_media(chromecast_url, 
                                   content_type = type)
            # unset cast confirmation
            cast_confirmed = 0 

            # Note the various specifics of play 
            cast_status = status
            cast_uri = uri
    

        # Status updates from Chromecast
        if (status != 'stop'):

            # We need an updated status from the Chromecast
            # This can fail sometimes when nothing is really wrong and 
            # then other times when things are wrong :)
            #
            # So we give it a tolerance of 5 consecutive failures
            try:
                cast_device.media_controller.update_status()
            except:
                failed_status_update_count += 1
                print("%s Failed to get chromecast status.. %d/5" % (
                    time.asctime(),
                    failed_status_update_count))

                if (failed_status_update_count >= 5):
                    print("%s Detected broken controller after 5 failures to get status" % (time.asctime()))
                    cast_device = None
                    cast_status = 'none'
                    cast_uri = 'none'
                    cast_volume = 0
                    cast_confirmed = 0
                    failed_status_update_count = 0
                    continue

            # Reset failed status count
            failed_status_update_count = 0

            cast_url = cast_device.media_controller.status.content_id
            cast_elapsed = int(cast_device.media_controller.status.current_time)

            # Length and progress calculation
            if cast_device.media_controller.status.duration is not None:
                duration = int(cast_device.media_controller.status.duration)
                progress = int(cast_elapsed / duration * 100)
            else:
                duration = 0
                progress = 0

            elapsed_mins = int(cast_elapsed / 60)
            elapsed_secs = cast_elapsed % 60
            duration_mins = int(duration / 60)
            duration_secs = duration % 60
            print("%s Chromecast.. Instance:%d Confirmed:%d State:%s Elapsed: %d:%02d/%d:%02d [%02d%%]" % (
                time.asctime(),
                ctrl_create_count,
                cast_confirmed,
                status,
                elapsed_mins,
                elapsed_secs,
                duration_mins,
                duration_secs,
                progress))

            # Confirm successful casting after observing 5 seconds play
            # Plays a role in better detecting idle state for next song
            if (status == 'play' and 
                    cast_elapsed > 5):
                cast_confirmed = 1

            # Detect end of play on chromecast
            # and nudge next song in playlist
            # We combine detection of idle state
            # and a previously casr_confirmed.
            # Otherwise we will get false positives after 
            # just starting playing and may skip tracks 
            # before they actually start.
            if (status == 'play' and 
                    cast_confirmed == 1 and 
                    cast_device.media_controller.status.player_is_idle):
                print("%s Request Next song" % (time.asctime()))
                cast_confirmed = 0
                resp = api_session.get('http://localhost:3000/api/v1/commands/?cmd=next')


            # sync local progress every 10 seconds
            # This is not exact and will likely keep volumio behind.
            # However we want to avoid volumio playback progress charging ahead 
            # of the chromecast progress as it could change track before the 
            # chromecast completes it playback.
            # We also limit this sync to confirmed casts and put a stop at 50% progress
            # as we'll be close enough by then.
            # We also ignore radio strems as sync does not apply to them
            # Had to do this sync as a system call to the volumio CLI
            # as there is no restful API call to match
            if (status == 'play' and 
                    cast_confirmed == 1 and 
                    cast_elapsed % 10 == 0 and 
                    progress < 50 and
                    not cast_uri.startswith('http')):
                print("%s Sync Chromecast elapsed to Volumio" % (time.asctime()))
                os.system("volumio seek %d >/dev/null 2>&1" % (cast_elapsed))
    


# main

parser = argparse.ArgumentParser(
        description='Volumio Chromecast Controller')

parser.add_argument('--name', 
                    help = 'Chromecast Friendly Name', 
                    default = "",
                    required = False)

parser.add_argument('--ip', 
                    help = 'Chromecast IP Address', 
                    default = "",
                    required = False)

parser.add_argument('--port', 
                    help = 'Chromecast Port (default )', 
                    default = 8009,
                    type = int,
                    required = False)

args = vars(parser.parse_args())
cast_name = args['name']
cast_ip = args['ip']
cast_port = args['port']

if (cast_name == "" and cast_ip == ""):
    print("Must specify Chromecast friendly name or IP address")
    sys.exit(-1)

if (cast_name != ""):
    print("Discovering Chromecasts.. looking for [%s]" % (cast_name))
    devices = pychromecast.get_chromecasts()
    
    cast_device = None
    for cc in devices:
        if (cc.device.friendly_name == cast_name):
            cast_device = cc
            print("Found device.. %s:%d" % (cast_device.host,
                                            cast_device.port))
            cast_ip = cast_device.host
            cast_port = cast_device.port
            break
    
    
    if (cast_device is None):
        print("Unable to find device")
        sys.exit(-1)


# Determine the main IP address
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(("8.8.8.8", 80))
server_ip = s.getsockname()[0]
s.close()


# Thread management and main loop
thread_list = []

# Cherry Py web server
web_server_t = threading.Thread(target = web_server)
web_server_t.daemon = True
web_server_t.start()
thread_list.append(web_server_t)

# Volumio Agent
volumio_t = threading.Thread(target = volumio_agent,
                             args = (cast_ip,
                                     cast_port,
                                     server_ip)
                             )
volumio_t.daemon = True
volumio_t.start()
thread_list.append(volumio_t)

while (1):
    dead_threads = 0
    for thread in thread_list:
         if (not thread.isAlive()):
             dead_threads += 1

    if (dead_threads > 0):
        print("Detected %d dead threads.. exiting" % (dead_threads))
        sys.exit(-1);

    time.sleep(5)


