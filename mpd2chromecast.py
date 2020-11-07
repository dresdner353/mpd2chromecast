#!/usr/bin/env python3
# coding=utf-8

import pychromecast
import mpd
import requests
import urllib
import threading
import argparse
import time
import os
import sys
import cherrypy
import json
import socket
import pathlib


def log_message(message):
    print("%s %s" % (
        time.asctime(),
        message))
    sys.stdout.flush()

# Config inits
gv_cfg_filename = ""
gv_chromecast_name = ""
gv_cast_port = 8080
gv_streamer_variant = "Unknown"
gv_discovered_devices = ['Off']

# Fixed MPD music location
# may make this configurable in time
gv_mpd_music_dir = '/var/lib/mpd/music'


def determine_streamer_variant():
    # Determine the stream variant we have
    # as some variations apply in how things work

    global gv_streamer_variant

    if (os.path.exists('/usr/local/bin/moodeutl') or
            os.path.exists('/usr/bin/moodeutl')):
        gv_streamer_variant = 'moOde'

    elif (os.path.exists('/usr/local/bin/volumio') or
            os.path.exists('/usr/bin/volumio')):
        gv_streamer_variant = 'Volumio'

    log_message('Streamer is identified as %s' % (
        gv_streamer_variant))



def get_chromecast():
    global gv_chromecast_name

    if (not gv_chromecast_name or 
            gv_chromecast_name == 'Off'):
        return None

    log_message("Connecting to Chromecast %s" % (gv_chromecast_name))
    try:
        devices, browser = pychromecast.get_listed_chromecasts(
                friendly_names=[gv_chromecast_name])
    except:
        log_message("Failed to get device object (Exception)")
        return None

    if len(devices) > 0:
        log_message("Got device object.. uuid:%s model:%s" % (
            devices[0].uuid,
            devices[0].model_name))
        return devices[0]
    
    log_message("Failed to get device object")
    return None


def load_config(cfg_filename):
    global gv_chromecast_name

    log_message("Loading config from %s" % (cfg_filename))
    cfg_file = open(cfg_filename, 'r')
    json_str = cfg_file.read()
    json_cfg = json.loads(json_str)
    cfg_file.close()

    gv_chromecast_name = json_cfg['chromecast']
    log_message("Set Chromecast device to [%s]" % (gv_chromecast_name))

    return


def config_agent():
    # monitor the config file and react on changes
    global gv_cfg_filename
    global gv_discovered_devices

    home = os.path.expanduser("~")
    gv_cfg_filename = home + '/.castrc'

    last_check = 0

    # 5-second check for config changes
    while (1):
        if os.path.exists(gv_cfg_filename):
            config_last_modified = os.path.getmtime(gv_cfg_filename)
            if config_last_modified > last_check:
                log_message("Detected update to %s" % (gv_cfg_filename))
                load_config(gv_cfg_filename)
                last_check = config_last_modified

        time.sleep(5)

    return 


def chromecast_agent():
    global gv_discovered_devices

    discovered_devices_file = '/tmp/castdevices'

    # initial load if the file exists
    if os.path.exists(discovered_devices_file):
        gv_discovered_devices = []
        with open(discovered_devices_file) as f:
            devices = f.read().splitlines()
            for device in devices:
                gv_discovered_devices.append(device)

    while (1):
        # only repeat once every 60 seconds
        time.sleep(60)

        try:
            devices, browser = pychromecast.get_chromecasts()
        except:
            log_message("Chromecast discovery failed")
            continue

        total_devices = len(devices)
        log_message("Discovered %d chromecasts" % (
            total_devices))

        gv_discovered_devices = []
        gv_discovered_devices.append('Off')
        total_devices += 1
        for cc in devices:
            gv_discovered_devices.append(cc.device.friendly_name)

        # Release all resources
        devices = None
        browser = None

        index = 0
        f = open(discovered_devices_file, "w")
        for device in gv_discovered_devices:
            index += 1
            log_message("%d/%d %s" % (
                index, 
                total_devices,
                device))
            f.write("%s\n" % (device))

        f.close()


    return 


def build_cast_web_page():
    global gv_discovered_devices
    global gv_chromecast_name

    header_tmpl = """
        <link rel='stylesheet' href='https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/css/bootstrap.min.css'>
        <script src='https://ajax.googleapis.com/ajax/libs/jquery/3.5.1/jquery.min.js'></script>
        <script src='https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/js/bootstrap.min.js'></script>
        <meta name="viewport" content="width=device-width, initial-scale=1">
    """

    web_page_str = header_tmpl

    # main container
    web_page_str += (
            '<div class="container-fluid">'
            '<div class="card" style="width: 18rem;">'
            ) 

    cast_icon_svg = (
            ' <svg width="2em" height="2em" viewBox="0 0 16 16" class="bi bi-cast" fill="currentColor" xmlns="http://www.w3.org/2000/svg">' 
            '   <path d="M7.646 9.354l-3.792 3.792a.5.5 0 0 0 .353.854h7.586a.5.5 0 0 0 .354-.854L8.354 9.354a.5.5 0 0 0-.708 0z"/>' 
            '   <path d="M11.414 11H14.5a.5.5 0 0 0 .5-.5v-7a.5.5 0 0 0-.5-.5h-13a.5.5 0 0 0-.5.5v7a.5.5 0 0 0 .5.5h3.086l-1 1H1.5A1.5 1.5 0 0 1 0 10.5v-7A1.5 1.5 0 0 1 1.5 2h13A1.5 1.5 0 0 1 16 3.5v7a1.5 1.5 0 0 1-1.5 1.5h-2.086l-1-1z"/>'
            ' </svg>'
            )

    # Chromecast combo box start
    web_page_str += (
            '<form action="/cast" method="post">'
            '<div class="input-group mb-3">'
            '%s &nbsp;'
            '<select class="custom-select custom-select" name="chromecast">'
            ) % (cast_icon_svg)

    for device in gv_discovered_devices:
        if device == gv_chromecast_name:
            selected_str = 'selected'
        else:
            selected_str = ''
        web_page_str += (
                '     <option value="%s" %s>%s</option>' % (
                    device, 
                    selected_str, 
                    device)
                )

    # Chromecast combo box end with action button
    web_page_str += (
            '</select>'
            '<button type="submit" class="btn btn-primary btn">Apply</button>'
            '</div>'
            '<a class="btn btn-primary btn" href="/cast" role="button">Refresh</a>'
            '</form>'
            )


    # main container
    web_page_str += (
            '</div>'
            '</div>'
            )

    return web_page_str


# dummy stream handler object for cherrypy
class stream_handler(object):
    pass


class cast_handler(object):
    @cherrypy.expose()

    def index(self, chromecast = None):
        global gv_chromecast_name

        log_message("device client:%s:%d params:%s" % (
            cherrypy.request.remote.ip,
            cherrypy.request.remote.port,
            cherrypy.request.params))

        if chromecast:
            log_message('Changing target chromecast to %s' % (
                chromecast))

            # Make change instantly
            gv_chromecast_name = chromecast

            # Also update config to make chanfge persistent
            home = os.path.expanduser("~")
            cfg_file = open(home + '/.castrc', 'w') 
            json_cfg = {}
            json_cfg['chromecast'] = chromecast
            cfg_file.write('%s\n' % (json.dumps(json_cfg)))
            cfg_file.close()

        return build_cast_web_page()

    # Force trailling slash off on called URL
    index._cp_config = {'tools.trailing_slash.on': False}


def web_server():
    global gv_cast_port
    global gv_mpd_music_dir

    # engine config
    cherrypy.config.update(
            {
                'environment': 'production',
                'log.screen': False,
                'log.access_file': '',
                'log.error_file': ''
            }
            )

    # Listen on our port on any IF
    cherrypy.server.socket_host = '0.0.0.0'
    cherrypy.server.socket_port = gv_cast_port

    # webhook for audio streaming
    # set up for directory serving
    # via /var/lib/mpd/music
    stream_conf = {
        '/music' : {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': gv_mpd_music_dir,
            'tools.staticdir.index': 'index.html',
        }
    }

    # Nothing special in play for the /cast API
    cast_conf = {}

    cherrypy.tree.mount(stream_handler(), '/', stream_conf)
    cherrypy.tree.mount(cast_handler(), '/cast', cast_conf)

    # Cherrypy main loop blocking
    cherrypy.engine.start()
    cherrypy.engine.block()


def mpd_file_to_url(mpd_file):
    global gv_server_ip
    global gv_cast_port

    # Radio/external stream
    # URL will start with http
    if mpd_file.startswith('http'):
        cast_url = mpd_file
        type = "audio/mp3"
    else:
        # Format file URL as path from our web server
        # mpd_file path is also made web-safe
        cast_url = "http://%s:%d/music/%s" % (
                gv_server_ip,
                gv_cast_port,
                urllib.parse.quote(mpd_file))

        # Split out extension of file
        # probably not necessary as chromecast seems to work it
        # out itself
        file, ext = os.path.splitext(mpd_file)
        type = "audio/%s" % (ext.replace('.', ''))

    return (cast_url, type)


def get_albumart_url(mpd_file):
    global gv_server_ip
    global gv_cast_port
    global gv_verbose

    # Ignore URLs
    if mpd_file.startswith('http'):
        return None

    art_names = [
            'cover.png',
            'cover.jpg',
            'cover.tiff',
            'cover.bmp',
            'cover.gif',
            ]

    albumart_url = None

    mpd_rel_path = pathlib.Path(mpd_file)
    mpd_full_path = pathlib.Path(gv_mpd_music_dir + '/' + mpd_file)

    for name in art_names:
        cover_file = str(mpd_full_path.parent / name)
        cover_rel_file = str(mpd_rel_path.parent / name)
        if os.path.exists(cover_file):
            albumart_url = "http://%s:%d/music/%s" % (
                    gv_server_ip,
                    gv_cast_port,
                    urllib.parse.quote(cover_rel_file))
            break

    return albumart_url


def mpd_agent():
    global gv_server_ip
    global gv_chromecast_name
    global gv_verbose

    mpd_client = None
    cast_device = None # initial state
    cast_name = ""

    failed_status_update_count = 0

    # Cast state inits
    cast_status = 'none'
    cast_file = 'none'
    cast_volume = 0

    mpd_elapsed = 0

    cast_confirmed = False
    
    while (1):
        # 1 sec delay per iteration
        time.sleep(1)
        print() # log output separator
        now = int(time.time())

        if not mpd_client:
            mpd_client = mpd.MPDClient()
            mpd_client.connect("localhost", 6600)

        # Get current MPD status details
        try:
            mpd_client_status = mpd_client.status()
            mpd_client_song = mpd_client.currentsong()
            if gv_verbose:
                log_message('MPD Status:\n%s' % (
                    json.dumps(
                        mpd_client_status, 
                        indent = 4)))
                log_message('MPD Current Song:\n%s' % (
                    json.dumps(
                        mpd_client_song, 
                        indent = 4)))
        except:
            # reset.. and let next loop reconect
            log_message('Problem getting mpd status')
            mpd_client = None
            continue

        # Start with the current playing/selected file
        mpd_file = 'none'
        if ('file' in mpd_client_song and 
                mpd_client_song['file']):
            mpd_file = mpd_client_song['file']

        # mandatory fields
        mpd_status = mpd_client_status['state']
        mpd_volume = int(mpd_client_status['volume'])

        # optionals (will depend on given state and stream vs file
        mpd_elapsed = 0
        mpd_duration = 0

        if 'elapsed' in mpd_client_status:
            mpd_elapsed = int(float(mpd_client_status['elapsed']))
        if 'duration' in mpd_client_status:
            mpd_duration = int(float(mpd_client_status['duration']))


        artist = ''
        album = ''
        title = ''
        if 'artist' in mpd_client_song:
            artist = mpd_client_song['artist']
        if 'album' in mpd_client_song:
            album = mpd_client_song['album']
        if 'title' in mpd_client_song:
            title = mpd_client_song['title']

        # Elapsed time and progress
        elapsed_mins = int(mpd_elapsed / 60)
        elapsed_secs = mpd_elapsed % 60
        duration_mins = int(mpd_duration / 60)
        duration_secs = mpd_duration % 60
        if mpd_duration > 0:
            progress = int(mpd_elapsed / mpd_duration * 100)
        else:
            progress = 0

        log_message("Current Track:%s/%s/%s" % (
            artist,
            album,
            title))

        log_message("MPD (%s) vol:%d %d:%02d/%d:%02d [%02d%%]" % (
            mpd_status,
            mpd_volume,
            elapsed_mins,
            elapsed_secs,
            duration_mins,
            duration_secs,
            progress))

        # Chromecast URL for media
        cast_url, cast_file_type = mpd_file_to_url(mpd_file)

        # Chromecast Status
        if (cast_device):

            # We need an updated status from the Chromecast
            # This can fail sometimes when nothing is really wrong and 
            # then other times when things are wrong :)
            #
            # So we give it a tolerance of 5 consecutive failures
            try:
                cast_device.media_controller.update_status()
                # Reset failed status count
                failed_status_update_count = 0
            except:
                failed_status_update_count += 1
                log_message("Failed to get chromecast status.. %d/5" % (
                    failed_status_update_count))

                if (failed_status_update_count >= 5):
                    log_message("Detected broken controller after 5 failures to get status")
                    cast_device = None
                    cast_status = 'none'
                    cast_file = 'none'
                    cast_volume = 0
                    failed_status_update_count = 0
                    continue

            cast_elapsed = int(cast_device.media_controller.status.current_time)

            # Length and progress calculation
            if cast_device.media_controller.status.duration is not None:
                cast_duration = int(cast_device.media_controller.status.duration)
                cast_progress = int(cast_elapsed / cast_duration * 100)
            else:
                cast_duration = 0
                cast_progress = 0

            elapsed_mins = int(cast_elapsed / 60)
            elapsed_secs = cast_elapsed % 60
            duration_mins = int(cast_duration / 60)
            duration_secs = cast_duration % 60
            log_message("%s (%s) vol:%02d %d:%02d/%d:%02d [%02d%%]" % (
                cast_name,
                cast_status,
                cast_volume,
                elapsed_mins,
                elapsed_secs,
                duration_mins,
                duration_secs,
                cast_progress))


        # Configured Chromecast change
        # Clear existing device handle
        if (cast_name != gv_chromecast_name):
            # Stop media player of existing device
            # if it exists
            if (cast_device):
                log_message("Detected Chromecast change from %s -> %s" % (
                    cast_name,
                    gv_chromecast_name))
                cast_device.media_controller.stop()
                cast_device.quit_app()
                cast_status = mpd_status
                cast_device = None
                continue

        # Get cast device when in play state and 
        # no device curently present
        if (mpd_status == 'play' and 
                not cast_device):
            cast_device = get_chromecast()
            cast_name = gv_chromecast_name

            if not cast_device:
                continue

            # Kill off any current app
            if not cast_device.is_idle:
                log_message("Killing current running app")
                cast_device.quit_app()

            while not cast_device.is_idle:
                log_message("Waiting for device to get ready..")
                time.sleep(1)

            # Cast state inits
            cast_status = 'none'
            cast_file = 'none'
            cast_volume = 0
            continue


        # MPD -> Chromecast Events
        # Anything that is driven from detecting changes
        # on the MPD side and pushing to the Chromecast
        if (not cast_device):
            continue

        # Initial Cast protection
        # In first 10 seconds after casting a file
        # we keep MPD paused only unpausing 
        # and re-seeking to cast_elapsed - 1 when the 
        # chromecast is reporting elapsed time
        if (not cast_confirmed and 
                mpd_status == 'pause' and 
                cast_status == 'play' and
                not cast_file.startswith('http')):
            if (cast_elapsed < 1):
                log_message('Initial cast.. Waiting for chromecast elapsed time')
            else:
                log_message('Initial cast.. Unpausing mpd')
                # sync 1 second behind
                mpd_client.seekcur(cast_elapsed - 1)
                # play (pause 0)
                mpd_client.pause(0)
                cast_confirmed = True
            continue


        # Volume change only while playing
        if (cast_status == 'play' and 
                cast_volume != mpd_volume):

            log_message("Setting Chromecast Volume: %d" % (mpd_volume))
            # Chromecast volume is 0.0 - 1.0 (divide by 100)
            cast_device.set_volume(mpd_volume / 100)
            cast_volume = mpd_volume
            continue

        # Pause
        if (cast_status != 'pause' and
            mpd_status == 'pause'):

            log_message("Pausing Chromecast")
            cast_device.media_controller.pause()
            cast_status = mpd_status
            continue
        
        # Resume play
        if (cast_status == 'pause' and 
            mpd_status == 'play'):

            log_message("Unpause Chromecast")
            cast_device.media_controller.play()
            cast_status = mpd_status
            continue
        
        # Stop
        if (cast_status != 'stop' and 
            mpd_status == 'stop'):

            log_message("Stop Chromecast")
            cast_device.media_controller.stop()
            cast_status = mpd_status
            cast_device = None
            cast_volume = 0
            continue

        # Play a song or stream or next in playlist
        if ((cast_status != 'play' and
            mpd_status == 'play') or
            (mpd_status == 'play' and mpd_file != cast_file)):

            log_message("Casting URL:%s type:%s" % (
                cast_url,
                cast_file_type))

            args = {}
            args['content_type'] = cast_file_type
            args['title'] = title
            args['autoplay'] = True

            albumart_url = get_albumart_url(mpd_file)
            if albumart_url:
                args['thumb'] = albumart_url
                log_message("Albumart URL:%s" % (
                    albumart_url))

            # Let the magic happen
            # Wait for the connection and then issue the 
            # URL to stream
            cast_device.wait()

            if (cast_volume != mpd_volume):
                # Set volume to match local MPD volume
                # avoids sudden volume changes after playback starts when 
                # they sync up
                log_message("Setting Chromecast Volume: %d" % (mpd_volume))
                # Chromecast volume is 0.0 - 1.0 (divide by 100)
                cast_device.set_volume(mpd_volume / 100)

            # Initiate the cast
            cast_device.media_controller.play_media(
                    cast_url, 
                    **args)

            # Note the various specifics of play 
            cast_status = mpd_status
            cast_file = mpd_file
            cast_volume = mpd_volume

            # Pause and seek to start of track
            # only applies to local files
            if (not cast_file.startswith('http')):
                log_message("Pausing MPD")
                mpd_client.pause(1)
                mpd_client.seekcur(0)
                cast_confirmed = False

            continue
    

        # Detect a skip on MPD and issue a seek request on the 
        # chromecast.
        # This feature can mis-fire depending on when its checked and 
        # what detail is present on the MPD status.
        # So we check that the chromecast is actively playing (cast_elapsed > 0)
        # Also check that there is a min of 3 seconds between the time the track was 
        # cast and curent timestamp. This prevents issues where the MPD status 
        # shows a new track but retains the old track elapsed time for 1-2 seconds
        # Finally we ensure there is at least 10 seconds difference between the 
        # two elapsed times to ensure it's not a false positive because of lag
        if (mpd_status == 'play' and 
                cast_status == 'play' and 
                not cast_file.startswith('http') and 
                cast_confirmed and
                cast_elapsed > 0 and
                abs(mpd_elapsed - cast_elapsed) >= 10):
            log_message(
                    "Sync MPD elapsed %d secs to Chromecast" % (
                        mpd_elapsed))
            cast_device.media_controller.seek(mpd_elapsed)
            continue 
    
        # Every 10 seconds sync Chromecast playback 
        # back to MPD elapsed time if mpd
        # is at the same time or further on.
        # Radio streams ignored for this.
        # The value we then set on mpd is 1 second 
        # behind the # chromecast elapsed time.
        # We want mpd preferentially 1 second behind the 
        # Chromecast to allow the chromecast complete the stream 
        # before it reacts to a track change
        if (mpd_status == 'play' and 
                not cast_file.startswith('http') and
                cast_elapsed > 0 and 
                cast_elapsed % 10 == 0 and
                (mpd_elapsed >= cast_elapsed or
                    mpd_elapsed < cast_elapsed - 1)):
                log_message(
                        "Sync Chromecast elapsed %d secs to MPD" % (
                            cast_elapsed))

                # Value for seek is 1 second behind
                mpd_client.seekcur(cast_elapsed - 1)

# main

parser = argparse.ArgumentParser(
        description='MPD Chromecast Agent')

parser.add_argument('--verbose', 
                    help = 'Enable verbose output', 
                    action = 'store_true')


args = vars(parser.parse_args())
gv_verbose = args['verbose']

# Determine the main IP address of the server
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(("8.8.8.8", 80))
gv_server_ip = s.getsockname()[0]
s.close()

# Determine variant
determine_streamer_variant()

# Thread management and main loop
thread_list = []

# Cherry Py web server
web_server_t = threading.Thread(target = web_server)
web_server_t.daemon = True
web_server_t.start()
thread_list.append(web_server_t)

# MPD Agent
mpd_t = threading.Thread(target = mpd_agent)
mpd_t.daemon = True
mpd_t.start()
thread_list.append(mpd_t)

# Config Agent
config_t = threading.Thread(target = config_agent)
config_t.daemon = True
config_t.start()
thread_list.append(config_t)

# Chromecast Agent
chromecast_t = threading.Thread(target = chromecast_agent)
chromecast_t.daemon = True
chromecast_t.start()
thread_list.append(chromecast_t)

while (1):
    dead_threads = 0
    for thread in thread_list:
         if (not thread.isAlive()):
             dead_threads += 1

    if (dead_threads > 0):
        log_message("Detected %d dead threads.. exiting" % (dead_threads))
        sys.exit(-1);

    time.sleep(5)


