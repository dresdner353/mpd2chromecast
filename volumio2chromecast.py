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

def log_message(message):
    print("%s %s" % (
        time.asctime(),
        message))
    sys.stdout.flush()

# Config inits
gv_cfg_filename = ""
gv_chromecast_name = ""

def get_chromecast():
    global gv_chromecast_name

    if not gv_chromecast_name:
        return None

    log_message("Discovering Chromecasts.. looking for [%s]" % (gv_chromecast_name))
    devices, browser = pychromecast.get_listed_chromecasts(
            friendly_names=[gv_chromecast_name])

    if len(devices) > 0:
        log_message("Got device object.. uuid:%s" % (devices[0].uuid))
        return devices[0]
    
    log_message("Failed to get device object")
    return None


def load_config():
    global gv_cfg_filename
    global gv_chromecast_name

    log_message("Loading config from %s" % (gv_cfg_filename))
    cfg_file = open(gv_cfg_filename, 'r')
    json_str = cfg_file.read()
    json_cfg = json.loads(json_str)
    cfg_file.close()

    gv_chromecast_name = json_cfg['chromecast']
    log_message("Set Chromecast device to [%s]" % (gv_chromecast_name))

    return


def config_init(name):
    global gv_chromecast_name
    global gv_cfg_filename

    gv_chromecast_name = name

    if (gv_chromecast_name == ""):
        # Determine home directory and cfg file
        # given no cmdline args used
        home = os.path.expanduser("~")
        gv_cfg_filename = home + '/.castrc'
        load_config()

    return


def config_agent():
    # monitor the config file and react on changes
    global gv_cfg_filename

    last_check = 0

    # 5-second check for config changes
    while (1):
        if os.path.exists(gv_cfg_filename):
            config_last_modified = os.path.getmtime(gv_cfg_filename)
            if config_last_modified > last_check:
                log_message("Detected update to %s" % (gv_cfg_filename))
                load_config()
                last_check = config_last_modified

        time.sleep(5)

    return 


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
       '/music': {
           'tools.staticdir.on': True,
           'tools.staticdir.dir': '/mnt',
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
        chromecast_url = "http://%s:8000/music/%s" % (server_ip,
                                                      uri)

        # Split out extension of file
        # probably not necessary as chromecast seems to work it
        # out itself
        file, ext = os.path.splitext(uri)
        type = "audio/%s" % (ext.replace('.', ''))

    return (chromecast_url, type)


def volumio_albumart_to_url(server_ip,
                            albumart):
    if albumart.startswith('http'):
        artwork_url = albumart
    else:
        # Format file URL as path to volumio
        # webserver plus the freaky albumart URI
        artwork_url = "http://%s/%s" % (server_ip,
                                        albumart)

    return (artwork_url)  


def volumio_agent():
    global gv_server_ip
    global gv_chromecast_name

    api_session = requests.session()

    cast_device = None # initial state
    cast_name = ""

    ctrl_create_count = 0
    failed_status_update_count = 0

    cc_host = ""
    cc_port = 0

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
            artist = json_resp['title']
            album = json_resp['album']
            title = json_resp['title']
            albumart = json_resp['albumart']
        except:
            log_message('Problem getting volumio status')
            continue

        log_message("Volumio State:\n%s\n" % (
            json.dumps(
                json_resp, 
                indent = 4)))

        # remove leading 'music-library' or 'mnt' if present
        # we're hosting from /mnt so we need remove the top-level
        # dir
        for prefix in ['music-library/', 'mnt/']:
            prefix_len = len(prefix)
            if uri.startswith(prefix):
                uri = uri[prefix_len:]

        volume = int(json_resp['volume']) / 100 # scale to 0.0 to 1.0 for Chromecast

        # Configured Chromecast change
        log_message("Current Device:%s Configured Device:%s" % (
            cast_name,
            gv_chromecast_name))
        if cast_name != gv_chromecast_name:
            log_message("Detected device change from %s -> %s" % (
                cast_name,
                gv_chromecast_name))
            # Stop media player of existing device
            # if it exists
            if (cast_device):
                log_message("Stopping casting via %s" % (cast_name))
                cast_device.media_controller.stop()
                cast_device.quit_app()
                cast_status = status
                cast_device = None

        # Chromecast URLs for media and artwork
        chromecast_url, type = volumio_uri_to_url(gv_server_ip, uri)
        albumart_url = volumio_albumart_to_url(gv_server_ip, albumart)
        log_message("Stream URL:%s" % (chromecast_url))
        log_message("Album Art URL:%s" % (albumart_url))

        # Controller management
        # Handles first creation of the controller and 
        # recreation of the controller after detection of stale connections
        # also only does this if we're in a play state
        if (status == 'play' and 
                cast_device is None):
            log_message("Connecting to Chromecast %s" % (
                gv_chromecast_name))
            cast_device = get_chromecast()
            cast_name = gv_chromecast_name

            if not cast_device:
                log_message("Failed to get cast device object")
                continue

            # Kill off any current app
            log_message("Waiting for device to get ready..")
            if not cast_device.is_idle:
                log_message("Killing current running app")
                cast_device.quit_app()

            while not cast_device.is_idle:
                time.sleep(1)

            log_message("Connected to %s (%s) model:%s" % (
                cast_device.name,
                cast_device.uuid,
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
        if (not cast_device):
            log_message("No active Chromecast device")
            continue

        # Detection of Events from Volumio
        # All of these next code blocks are trying to compare
        # some property against a known cast equivalent to determine 
        # a change has occured and action required

        # Volume change only while playing
        if (cast_volume != volume and
                cast_status == 'play'):

            log_message("Setting Chromecast Volume: %.2f" % (volume))
            cast_device.set_volume(volume)
            cast_volume = volume
    
        # Pause
        if (cast_status != 'pause' and
            status == 'pause'):

            log_message("Pausing Chromecast")
            cast_device.media_controller.pause()
            cast_status = status
        
        # Resume play
        if (cast_status == 'pause' and 
            status == 'play'):

            log_message("Unpause Chromecast")
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
                log_message("Stop Chromecast")
                cast_device.media_controller.stop()
                cast_status = status
                cast_device = None

            elif (uri != cast_uri):
                # track switch
                log_message("Casting URL (paused):%s type:%s" % (
                    chromecast_url.encode('utf-8'),
                    type))

                # Prep for playback but paused
                # autoplay = False
                cast_device.play_media(chromecast_url, 
                                       content_type = type,
                                       title = title,
                                       thumb = albumart_url,
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

            log_message("Casting URL:%s type:%s" % (
                chromecast_url.encode('utf-8'),
                type))

            # Let the magic happen
            # Wait for the connection and then issue the 
            # URL to stream
            cast_device.wait()
            cast_device.media_controller.play_media(
                    chromecast_url, 
                    content_type = type,
                    title = title,
                    thumb = albumart_url,
                    autoplay = True)

            # unset cast confirmation
            # Will be set again once we confirm 
            # it is streaming
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
                log_message("Failed to get chromecast status.. %d/5" % (
                    failed_status_update_count))

                if (failed_status_update_count >= 5):
                    log_message("Detected broken controller after 5 failures to get status")
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
            log_message("Chromecast.. Instance:%d Confirmed:%d State:%s Elapsed: %d:%02d/%d:%02d [%02d%%]" % (
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
            # and a previously cast_confirmed.
            # Otherwise we will get false positives after 
            # just starting playing and may skip tracks 
            # before they actually start.
            if (status == 'play' and 
                    cast_confirmed == 1 and 
                    cast_device.media_controller.status.player_is_idle):
                log_message("Request Next song")
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
            if (status == 'play' and 
                    cast_confirmed == 1 and 
                    cast_elapsed % 10 == 0 and 
                    progress < 50 and
                    not cast_uri.startswith('http')):
                log_message("Sync Chromecast elapsed %d secs to Volumio" % (cast_elapsed))
                resp = api_session.get('http://localhost:3000/api/v1/commands/?cmd=seek&position=%d' % (cast_elapsed))
    


# main

parser = argparse.ArgumentParser(
        description='Volumio Chromecast Agent')

parser.add_argument('--name', 
                    help = 'Chromecast Friendly Name', 
                    default = "",
                    required = False)

args = vars(parser.parse_args())
gv_chromecast_name = args['name']

# Init config
config_init(gv_chromecast_name)

# Determine the main IP address of the server
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(("8.8.8.8", 80))
gv_server_ip = s.getsockname()[0]
s.close()

# Thread management and main loop
thread_list = []

# Cherry Py web server
web_server_t = threading.Thread(target = web_server)
web_server_t.daemon = True
web_server_t.start()
thread_list.append(web_server_t)

# Volumio Agent
volumio_t = threading.Thread(target = volumio_agent)
volumio_t.daemon = True
volumio_t.start()
thread_list.append(volumio_t)

if (gv_cfg_filename != ""):
    # Config server thread if we're set to 
    # drive config from a file. that we we can 
    # handle updates
    config_t = threading.Thread(target = config_agent)
    config_t.daemon = True
    config_t.start()
    thread_list.append(config_t)

while (1):
    dead_threads = 0
    for thread in thread_list:
         if (not thread.isAlive()):
             dead_threads += 1

    if (dead_threads > 0):
        log_message("Detected %d dead threads.. exiting" % (dead_threads))
        sys.exit(-1);

    time.sleep(5)


