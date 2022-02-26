#!/usr/bin/env python3
# coding=utf-8

import pychromecast
import zeroconf
import mpd
import requests
import urllib
import concurrent.futures
import argparse
import time
import os
import sys
import cherrypy
import json
import socket
import pathlib
import traceback


def log_message(verbose,
        message):
    if verbose:
        print('%s %s' % (
            time.asctime(),
            message))
        sys.stdout.flush()

    return

# Config inits
gv_cfg_filename = ''
gv_cfg_dict = {}
gv_cfg_dict['castDevice'] = 'Disabled'
gv_cfg_dict['castMode'] = 'bogus'
gv_cast_port = 8090
gv_platform_variant = 'Unknown'
gv_stream_albumart_dir = None
gv_stream_albumart_file = None

# Discovered cast devices dict
# and related zconf object
gv_cast_devices_dict = {}
gv_zconf = None

# Fixed MPD music location
# may make this configurable in time
gv_mpd_music_dir = '/var/lib/mpd/music'

# Global MPD agent deadlock timestamp
gv_mpd_agent_timestamp = 0


def determine_platform_variant():
    # Determine the stream variant we have
    # as some variations apply in how things work

    global gv_platform_variant
    global gv_stream_albumart_dir
    global gv_stream_albumart_file

    platform_name_dict = {
            'moodeutl' : 'moOde',
            'volumio' : 'Volumio',
            }

    gv_platform_variant = 'Unknown'
    for bin_file in platform_name_dict:
        if (os.path.exists('/usr/local/bin/' + bin_file) or
                os.path.exists('/usr/bin/' + bin_file)):
            gv_platform_variant = platform_name_dict[bin_file]
            break

    log_message(
            1,
            'Platform is identified as %s' % (
                gv_platform_variant))

    albumart_list = [
            '/var/www/images/default-cover-v6.svg',
            '/volumio/app/plugins/miscellanea/albumart/default.jpg'
            ]

    for albumart_file in albumart_list:
        if os.path.exists(albumart_file):
            gv_stream_albumart_dir = os.path.dirname(albumart_file)
            gv_stream_albumart_file = os.path.basename(albumart_file)
            break



def get_cast_device(name):
    global gv_cast_devices_dict
    global gv_zconf

    if (not name or 
            name == 'Disabled'):
        return None

    log_message(
            1,
            'Looking up Cast Device [%s]' % (name))

    if not gv_zconf:
        log_message(
                1, 
                'No zconf service active')
        return None

    if not name in gv_cast_devices_dict:
        log_message(
                1,
                'cast device not found in discovered device services')
        return None

    try:
        log_message(
                1,
                'Getting cast device object')
        # Get the device handle
        # FIXME this call has issues
        device = pychromecast.get_chromecast_from_cast_info(
                gv_cast_devices_dict[name],
                gv_zconf)
    except:
        traceback.print_exc()
        log_message(
                1,
                'Failed to get cast device object')
        device = None

    return device


def load_config():
    global gv_cfg_filename
    global gv_cfg_dict

    log_message(
            1,
            'Loading config from %s' % (gv_cfg_filename))
    cfg_file = open(gv_cfg_filename, 'r')
    json_str = cfg_file.read()
    gv_cfg_dict = json.loads(json_str)
    cfg_file.close()

    log_message(
            1,
            'Config [%s]' % (
                gv_cfg_dict))

    return 


def save_config():
    global gv_cfg_filename
    global gv_cfg_dict

    log_message(
            1,
            'Saving config to %s' % (gv_cfg_filename))
    cfg_file = open(gv_cfg_filename, 'w') 
    cfg_file.write('%s\n' % (json.dumps(gv_cfg_dict)))
    cfg_file.close()

    return 


def config_agent():
    global gv_cfg_filename

    # monitor the config file and react on changes
    home = os.path.expanduser('~')
    gv_cfg_filename = home + '/.mpd2chromecast'   
    log_message(
            1,
            'Config file is %s' % (gv_cfg_filename))

    last_check = 0

    # 5-second check for config changes
    while (True):
        if os.path.exists(gv_cfg_filename):
            config_last_modified = os.path.getmtime(gv_cfg_filename)
            if config_last_modified > last_check:
                log_message(
                        2,
                        'Detected update to %s' % (
                            gv_cfg_filename))
                load_config()
                last_check = config_last_modified

        time.sleep(5)

    return 


def cast_device_discovery_agent():
    global gv_cast_devices_dict
    global gv_zconf

    def cast_device_add_callback(uuid, name):
        # Add discovered device to global dict
        # keyed on friendly name and stores the full 
        # service record
        friendly_name = cast_listener.services[uuid][3]
        gv_cast_devices_dict[friendly_name] = cast_listener.services[uuid]

    def cast_device_remove_callback(uuid, name, service):
        # purge removed devices from the global dict
        friendly_name = cast_listener.services[uuid][3]
        if friendly_name in gv_cast_devices_dict:
            del gv_cast_devices_dict[friendly_name]

    # cast listener (add, remove, update)
    # treat update as add
    cast_listener = pychromecast.CastListener(
            cast_device_add_callback,
            cast_device_remove_callback,
            cast_device_add_callback)

    gv_zconf = zeroconf.Zeroconf()
    cast_browser = pychromecast.discovery.start_discovery(
            cast_listener, 
            gv_zconf)

    while (True):
        time.sleep(30)
        log_message(
                0,
                'All discovered cast devices: %s' % (
            list(gv_cast_devices_dict.keys())))

    return 


def build_cast_web_page(refresh_interval = 10000):
    global gv_cast_devices_dict
    global gv_mpd_client_song
    global gv_verbose
    global gv_cfg_dict

    log_message(
            gv_verbose,
            'Building /cast webpage with refresh of %d msecs' % (
            refresh_interval))

    web_page_tmpl = """
        <head>   
        <link rel="stylesheet" href="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/css/bootstrap.min.css">
        <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
        <script src="https://ajax.googleapis.com/ajax/libs/jquery/3.5.1/jquery.min.js"></script>
        <script src="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/js/bootstrap.bundle.min.js"></script>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
          .material-icons.md-18 { font-size: 18px; }
          .material-icons.md-24 { font-size: 24px; }
          .material-icons.md-36 { font-size: 36px; }
          .material-icons.md-48 { font-size: 48px; }

        </style>
        <title>__TITLE__</title>

        <script>

        $(document).ready(function(){
        __ACTION_FUNCTIONS__
        });

        // Window focus awareness
        // for refresh page behaviour
        var window_focus = true;

        $(window).focus(function() {
            window_focus = true;
        }).blur(function() {
            window_focus = false;
        });

        // refresh timer and function
        // We use an interval refresh which will be called
        // every __RELOAD__ msecs and will invoke a reload of 
        // data into the dashboard div if the window is in focus
        // If not, we will skip the reload.
        // We also cancel the timer ahead of calling the reload to 
        // avoid the reload stacking more timers on itself and 
        // causing major issues
        var refresh_timer = setInterval(refreshPage, __RELOAD__);
        
        function refreshPage() {
            if (window_focus == true) {
                $.get("__REFRESH_URL__", function(data, status){
                    clearInterval(refresh_timer);
                    $("#dashboard").html(data);
                });
            }
        }

        </script>
        </head>   
        <body>
            <div id="dashboard">__DASHBOARD__</div>
        </body>
    """

    # action code for combos
    # click function resets refresh timer to 
    # 2 minutes
    change_get_reload_template = """
        $('#__ID__').on('change', function() {
            $.get('/cast?__ID__=' + this.value, function(data, status) {
                // clear refresh timer before reload
                clearInterval(refresh_timer);
                $("#dashboard").html(data);
            });
        });

        $('#__ID__').on('click', function() {
          // opened combo.. set refresh to a longer interval
          clearInterval(refresh_timer);
          refresh_timer = setInterval(refreshPage, 120000);
        })

    """


    dashboard_str = ''
    jquery_str = ''

    # main container and card
    dashboard_str += (
            '<div class="container-fluid">'
            '<div class="card">'
            '<div class="card-body">'
            ) 

    # Cast Device Combo
    dashboard_str += (
            '<div class="input-group mb-3">'
            '<i class="material-icons md-36">%s</i>&nbsp;'
            '<select class="custom-select custom-select" id="castDevice" name="castDevice">'
            ) % (
                    'cast_connected' if gv_cfg_dict['castDevice'] != 'Disabled' else 'cast'
                    )

    # Construct a sorted list of discovered device names
    # and put 'Disabled' at the top
    device_list = ['Disabled']
    device_list += sorted(list(gv_cast_devices_dict.keys()))

    for device in device_list:
        if device == gv_cfg_dict['castDevice']:
            selected_str = 'selected'
        else:
            selected_str = ''
        dashboard_str += (
                '<option value="%s" %s>%s</option>' % (
                    device, 
                    selected_str, 
                    device)
                )

    # Cast device combo box end
    dashboard_str += (
            '</select>'
            '</div>'
            )

    # action code for selecting a cast device
    action_str = change_get_reload_template
    action_str = action_str.replace('__ID__', 'castDevice')
    jquery_str += action_str

    # Cast Mode Combo
    dashboard_str += (
            '<div class="input-group mb-3">'
            '<i class="material-icons md-36">play_circle</i>&nbsp;'
            '<select class="custom-select custom-select" id="castMode" name="castMode">'
            )  

    cast_mode_list = ['direct', 'mpd']
    cast_mode_dict = {
            'direct' : 'Cast file URL (default)',
            'mpd' : 'Cast MPD Output Stream (experimental)'
            }

    for cast_mode in cast_mode_list:
        if cast_mode == gv_cfg_dict['castMode']:
            selected_str = 'selected'
        else:
            selected_str = ''
        dashboard_str += (
                '<option value="%s" %s>%s</option>' % (
                    cast_mode, 
                    selected_str, 
                    cast_mode_dict[cast_mode])
                )

    # Cast mode combo box end
    dashboard_str += (
            '</select>'
            '</div>'
            )

    # action code for selecting a cast mode
    action_str = change_get_reload_template
    action_str = action_str.replace('__ID__', 'castMode')
    jquery_str += action_str

    # Close outer dv
    dashboard_str += (
            '</div>'
            '</div>'
            '</div>'
            )

    # Final web page construction
    # refresh timer based on arg passed in to the function
    web_page_str = web_page_tmpl
    web_page_str = web_page_str.replace('__TITLE__', 'mpd2chromecast Control Panel')
    web_page_str = web_page_str.replace('__ACTION_FUNCTIONS__', jquery_str)
    web_page_str = web_page_str.replace('__DASHBOARD__', dashboard_str)
    web_page_str = web_page_str.replace('__REFRESH_URL__', '/cast')
    web_page_str = web_page_str.replace('__RELOAD__', str(refresh_interval))

    return web_page_str


# dummy stream handler object for cherrypy
class stream_handler(object):
    pass


class cast_handler(object):
    @cherrypy.expose()

    def index(
            self, 
            castDevice = None,
            castMode = None):

        global gv_verbose
        global gv_cfg_dict

        log_message(
                gv_verbose,
                '/cast API %s params:%s' % (
                    cherrypy.request.remote.ip,
                    cherrypy.request.params))

        # refresh defaults to 10k msecs
        # but refreshes at 3 seconds if an action is present
        if len(cherrypy.request.params) > 0:
            refresh_interval = 3000
        else:
            refresh_interval = 10000

        save_required = False

        if castDevice:
            log_message(
                    gv_verbose,
                    '/cast device -> %s' % (
                        castDevice))

            # Make change instantly and save
            gv_cfg_dict['castDevice'] = castDevice
            save_required = True

        if castMode:
            log_message(
                    gv_verbose,
                    '/cast mode -> %s' % (
                        castMode))

            # Make change instantly and save
            gv_cfg_dict['castMode'] = castMode
            save_required = True

        if save_required:
            save_config()

        return build_cast_web_page(refresh_interval)

    # Force trailling slash off on called URL
    index._cp_config = {'tools.trailing_slash.on': False}


def web_server():
    global gv_cast_port
    global gv_mpd_music_dir
    global gv_stream_albumart_dir
    global gv_stream_albumart_file

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

    # /cast API
    # mapped to /cast and /
    cast_conf = {}
    cherrypy.tree.mount(cast_handler(), '/cast', cast_conf)
    cherrypy.tree.mount(cast_handler(), '/', cast_conf)

    # /music handler for streaming
    # and file artwork
    stream_conf = {
        '/' : {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': gv_mpd_music_dir,
            'tools.staticdir.index': 'index.html',
        }
    }
    cherrypy.tree.mount(stream_handler(), '/music', stream_conf)

    # Stream Albumart dir used to serve static
    # splash for MPD streams
    if gv_stream_albumart_file:
        stream_albumart_conf = {
                '/' : {
                    'tools.staticdir.on': True,
                    'tools.staticdir.dir': gv_stream_albumart_dir,
                    'tools.staticdir.index': 'index.html',
                    }
                }
        cherrypy.tree.mount(stream_handler(), '/albumart', stream_albumart_conf)

    # Cherrypy main loop blocking
    cherrypy.engine.start()
    cherrypy.engine.block()


def mpd_file_to_url(mpd_file):
    global gv_server_ip
    global gv_cast_port

    # Radio/external stream
    # URL will start with http
    if (mpd_file.startswith('http://') or 
            mpd_file.startswith('https://')):
        cast_url = mpd_file
        mime_type = 'audio/mp3' # guess
        stream_type = 'radio'
    else:
        # Format file URL as path from our web server
        # mpd_file path is also made web-safe
        cast_url = 'http://%s:%d/music/%s' % (
                gv_server_ip,
                gv_cast_port,
                urllib.parse.quote(mpd_file))

        # Split out extension of file
        file, ext = os.path.splitext(mpd_file)
        mime_type = 'audio/%s' % (ext.replace('.', ''))
        stream_type = 'file'

    return (cast_url, mime_type, stream_type)


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
            albumart_url = 'http://%s:%d/music/%s' % (
                    gv_server_ip,
                    gv_cast_port,
                    urllib.parse.quote(cover_rel_file))
            break

    return albumart_url


def get_mpd_stream_albumart_url():
    global gv_server_ip
    global gv_cast_port
    global gv_verbose
    global gv_stream_albumart_file

    if not gv_stream_albumart_file:
        return None

    albumart_url = 'http://%s:%d/albumart/%s' % (
            gv_server_ip,
            gv_cast_port,
            urllib.parse.quote(gv_stream_albumart_file))

    return albumart_url


def mpd_file_agent():
    global gv_server_ip
    global gv_verbose
    global gv_mpd_agent_timestamp
    global gv_cfg_dict

    now = int(time.time())

    # MPD inits
    mpd_client = None
    mpd_last_status = now

    # Cast state inits
    cast_device = None # initial state
    cast_name = ''
    cast_status = 'none'
    cast_id = -1
    cast_volume = 0
    cast_confirmed = False
    cast_failed_update_count = 0
    max_cast_failed_updates = 20

    loop_count = -1
    
    while (True):
        loop_count += 1

        if gv_cfg_dict['castMode'] != 'direct':
            log_message(1, 'Exiting MPD File agent (config change)')
            return

        # 1 sec delay per iteration
        time.sleep(1)

        print() # log output separator
        now = int(time.time())

        # Timestamp loop activity for MPD agent
        # acts as a deadlock detection in main loop
        gv_mpd_agent_timestamp = now

        # MPD healthcheck
        if now - mpd_last_status > 60:
            log_message(
                    1,
                    'No MPD contact in 60 seconds... exiting')
            return

        if not mpd_client:
            log_message(
                    1,
                    'Connecting to MPD...')
            try:
                mpd_client = mpd.MPDClient()
                mpd_client.connect('localhost', 6600)
            except:
                log_message(
                        1,
                        'Problem getting mpd client')
                mpd_client = None
                continue

        # Get current MPD status details
        try:
            mpd_client_status = mpd_client.status()
            mpd_client_song = mpd_client.currentsong()

            log_message(
                    gv_verbose,
                    'MPD Status:\n%s' % (
                        json.dumps(
                            mpd_client_status, 
                            indent = 4)))
            log_message(
                    gv_verbose,
                    'MPD Current Song:\n%s' % (
                        json.dumps(
                            mpd_client_song, 
                            indent = 4)))

            mpd_last_status = now

        except:
            # reset... and let next loop reconect
            log_message(
                    1,
                    'Problem getting mpd status')
            mpd_client = None
            mpd_client_status = None
            mpd_client_song = None
            continue

        # sanity check on status
        # as it can come back empty
        if len(mpd_client_status) == 0:
            log_message(
                    1,
                    'Problem getting mpd status')
            continue

        # Start with the current playing/selected file
        mpd_file = None
        mpd_id = -1
        if ('file' in mpd_client_song and 
                mpd_client_song['file']):
            mpd_file = mpd_client_song['file']
            mpd_id = mpd_client_song['id']

        # mandatory fields
        mpd_status = mpd_client_status['state']

        # optional fields
        if 'volume' in mpd_client_status:
            mpd_volume = int(mpd_client_status['volume'])
        else:
            mpd_volume = -1 # used to track unknown value

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
            # Take first artist if is a list
            if type(artist) == list:
                artist = artist[0]
        if 'album' in mpd_client_song:
            album = mpd_client_song['album']
        if 'title' in mpd_client_song:
            title = mpd_client_song['title']

        # MPD Elapsed time and progress
        mpd_elapsed_mins = int(mpd_elapsed / 60)
        mpd_elapsed_secs = mpd_elapsed % 60
        mpd_duration_mins = int(mpd_duration / 60)
        mpd_duration_secs = mpd_duration % 60
        if mpd_duration > 0:
            mpd_progress = int(mpd_elapsed / mpd_duration * 100)
        else:
            mpd_progress = 0

        log_message(
                1,
                'Current Track:%s/%s/%s' % (
                    artist,
                    album,
                    title))

        log_message(
                1,
                'MPD (%s) vol:%s %d:%02d/%d:%02d [%02d%%]' % (
                    mpd_status,
                    'N/A' if mpd_volume == -1 else mpd_volume,
                    mpd_elapsed_mins,
                    mpd_elapsed_secs,
                    mpd_duration_mins,
                    mpd_duration_secs,
                    mpd_progress))

        # Cast Device Status
        if (cast_device):

            # We need an updated status from the Cast Device
            # This can fail sometimes when nothing is really wrong and 
            # then other times when things are wrong :)
            #
            # So we give it a tolerance of 20 consecutive failures
            try:
                cast_device.media_controller.update_status()
                # Reset failed status count
                cast_failed_update_count = 0
            except:
                cast_failed_update_count += 1
                log_message(
                        1,
                        'Failed to get cast device status... %d/%d' % (
                            cast_failed_update_count,
                            max_cast_failed_updates))

                if (cast_failed_update_count >= max_cast_failed_updates):
                    log_message(
                            1,
                            'Detected broken controller after %d status failures' % (
                                max_cast_failed_updates))
                    cast_device = None
                    cast_status = 'none'
                    cast_id = -1
                    cast_volume = 0
                    cast_failed_update_count = 0
                    continue

            # Elapsed time as reported by the cast device
            cast_elapsed = int(cast_device.media_controller.status.current_time)
            # Cast player state as reported by the device
            cast_player_state = cast_device.media_controller.status.player_state
            # Length and progress calculation
            if cast_device.media_controller.status.duration is not None:
                cast_duration = int(cast_device.media_controller.status.duration)
                cast_progress = int(cast_elapsed / cast_duration * 100)
            else:
                cast_duration = 0
                cast_progress = 0

            cast_elapsed_mins = int(cast_elapsed / 60)
            cast_elapsed_secs = cast_elapsed % 60
            cast_duration_mins = int(cast_duration / 60)
            cast_duration_secs = cast_duration % 60

            log_message(
                    1,
                    '%s (%s) [file] vol:%s %d:%02d/%d:%02d [%02d%%]' % (
                        cast_name,
                        cast_status,
                        'N/A' if mpd_volume == -1 else cast_volume,
                        cast_elapsed_mins,
                        cast_elapsed_secs,
                        cast_duration_mins,
                        cast_duration_secs,
                        cast_progress))


        # Configured Cast Device change
        # Clear existing device handle
        if (cast_name != gv_cfg_dict['castDevice']):
            # Stop media player of existing device
            # if it exists
            if (cast_device):
                log_message(
                        1,
                        'Detected Cast Device change from %s -> %s' % (
                            cast_name,
                            gv_cfg_dict['castDevice']))
                cast_device.media_controller.stop()
                cast_device.quit_app()
                cast_status = mpd_status
                cast_device = None
                cast_volume = 0
                continue

        # Cast Device URL for media
        # derived into a file URL (streaming)
        if mpd_file:
            cast_url, cast_mime_type, stream_type = mpd_file_to_url(mpd_file)
        else:
            # no file to stream -> stop casting 
            if (cast_device):
                log_message(
                        1,
                        'No current track.. Stopping Cast App')
                cast_device.media_controller.stop()
                cast_device.quit_app()
                cast_status = mpd_status
                cast_device = None
                cast_volume = 0

            continue

        # Get cast device when in play state and 
        # no device curently present
        if (mpd_status == 'play' and 
                not cast_device):
            cast_device = get_cast_device(gv_cfg_dict['castDevice'])
            cast_name = gv_cfg_dict['castDevice']

            # nothing to do if this fails
            if not cast_device:
                continue

            # Kill off any current app
            if not cast_device.is_idle:
                log_message(
                        1,
                        'Killing current running cast app')
                cast_device.quit_app()

            while not cast_device.is_idle:
                log_message(
                        1,
                        'Waiting for cast device to get ready...')
                time.sleep(1)

            # Cast state inits
            cast_status = 'none'
            cast_id = -1
            cast_volume = 0
            continue


        # MPD -> Cast Device Events
        # Anything that is driven from detecting changes
        # on the MPD side and pushing to the Cast Device

        # Nothing to do if we don't have a cast
        # device handle
        if (not cast_device):
            continue

        # Volume change only while playing
        if (cast_status == 'play' and 
                mpd_volume != -1 and 
                cast_volume != mpd_volume):

            log_message(
                    1,
                    'Setting Cast Device Volume: %d' % (mpd_volume))
            # Cast Device volume is 0.0 - 1.0 (divide by 100)
            cast_device.set_volume(mpd_volume / 100)
            cast_volume = mpd_volume
            continue

        # Stop event
        # stop and quit cast app
        if (cast_status != 'stop' and 
            mpd_status == 'stop' and
            cast_device):

            log_message(
                    1,
                    'Stopping Cast App')
            cast_device.media_controller.stop()
            cast_device.quit_app()
            cast_status = mpd_status
            cast_device = None
            cast_volume = 0
            continue  

        # Initial Cast protection for file streaming
        # After an initial cast we pause MPD 
        # only unpausing and re-seeking to 
        # cast_elapsed - 1 when the 
        # cast device is reporting elapsed time
        # Does not apply for radio streams
        if (stream_type == 'file' and 
                not cast_confirmed and 
                mpd_status == 'pause' and 
                cast_status == 'play'):
            if (cast_elapsed == 0):
                log_message(
                        1,
                        'Initial cast... Waiting for cast device elapsed time')
            else:
                log_message(
                        1,
                        'Initial cast... elapsed time detected.. Unpausing mpd')
                # sync 1 second behind
                mpd_client.seekcur(cast_elapsed - 1)
                # play (pause 0)
                mpd_client.pause(0)
                cast_confirmed = True
            continue

        # Pause file stream only
        if (stream_type == 'file' and 
                cast_status != 'pause' and
                mpd_status == 'pause'):

            log_message(
                    1,
                    'Pausing Cast Device')
            cast_device.media_controller.pause()
            cast_status = mpd_status
            continue
        
        # Resume play
        # but only if the track is the same
        # needed to protect a scenario where we pause
        # and then change track
        # prevents a brief unpause of play before the sudden
        # change
        if (mpd_id == cast_id and
                cast_status == 'pause' and 
            mpd_status == 'play'):

            log_message(
                    1,
                    'Unpause Cast Device')
            cast_device.media_controller.play()
            cast_status = mpd_status
            continue
        
        # Play a song/stream or next in playlist
        # triggered by:
        # 1) different play states between mpd and cast device,
        # 2) different mpd/cast IDs (playlist change)
        # 3) cast device is IDLE and mpd_elapsed at 0 (repeat same track)
        if (mpd_status == 'play' and 
                (cast_status != 'play' or 
                    mpd_id != cast_id or 
                    (mpd_elapsed == 0 and 
                        cast_player_state == 'IDLE'))):

            log_message(
                    1,
                    'Casting URL:%s type:%s' % (
                        cast_url,
                        cast_mime_type))

            args = {}
            args['content_type'] = cast_mime_type
            args['title'] = title
            args['autoplay'] = True

            # metadata MusicTrackMediaMetadata (3)
            # Lets us push Artist and Album name
            args['metadata'] = {}
            args['metadata']['metadataType'] = 3 
            args['metadata']['artist'] = artist
            args['metadata']['albumName'] = album

            albumart_url = get_albumart_url(mpd_file)
            if albumart_url:
                args['thumb'] = albumart_url
                log_message(
                        1,
                        'Albumart URL:%s' % (
                            albumart_url))

            # Let the magic happen
            # Wait for the connection and then issue the 
            # URL to stream
            cast_device.wait()

            if (mpd_volume != -1 and 
                    cast_volume != mpd_volume):
                # Set volume to match local MPD volume
                # avoids sudden volume changes after playback starts when 
                # they sync up
                log_message(
                        1,
                        'Setting Cast Device Volume: %d' % (mpd_volume))
                # Cast Device volume is 0.0 - 1.0 (divide by 100)
                cast_device.set_volume(mpd_volume / 100)
                cast_volume = mpd_volume

            # Initiate the cast
            print(args)
            cast_device.media_controller.play_media(
                    cast_url, 
                    **args)

            # Note the various specifics of play 
            cast_status = mpd_status
            cast_id = mpd_id

            # Pause and seek to start of track
            # applies to local files and radio streams
            log_message(
                    1,
                    'Pausing MPD (initial cast)')
            mpd_client.pause(1)
            mpd_client.seekcur(0)
            cast_confirmed = False

            # no more to do until next loop
            continue

        # Detect a skip on MPD and issue a seek request on 
        # the cast device.
        #
        # Make sure the cast is confirmed and only perform the
        # seek if there is a difference of min 10 seconds
        # That prevents mis-fire if the two elapsed times are 
        # just out of sync versus an actual mpd seek being performed
        if (stream_type == 'file' and
                mpd_status == 'play' and 
                cast_status == 'play' and 
                cast_confirmed and 
                cast_elapsed > 0 and 
                abs(mpd_elapsed - cast_elapsed) >= 10):
            log_message(
                    1,
                    'Sync MPD elapsed %d secs to Cast Device' % (
                        mpd_elapsed))
            cast_device.media_controller.seek(mpd_elapsed)
            continue 
    
        # Every 10 seconds sync cast device playback 
        # back to MPD elapsed time if mpd
        # is at the same time or further on.
        # Radio streams ignored for this.
        # The value we then set on mpd is 1 second 
        # behind the cast device elapsed time.
        if (stream_type == 'file' and
                mpd_status == 'play' and 
                cast_elapsed > 0 and 
                cast_elapsed % 10 == 0 and
                (mpd_elapsed >= cast_elapsed or
                    mpd_elapsed < cast_elapsed - 1)):
                log_message(
                        1,
                        'Sync Cast Device elapsed %d secs to MPD' % (
                            cast_elapsed))

                # Value for seek is 1 second behind
                mpd_client.seekcur(cast_elapsed - 1)


def mpd_stream_agent():
    global gv_server_ip
    global gv_verbose
    global gv_mpd_agent_timestamp
    global gv_cfg_dict

    now = int(time.time())

    # MPD inits
    mpd_client = None
    mpd_last_status = now

    # Cast state inits
    cast_device = None # initial state
    cast_name = ''
    cast_status = 'none'
    cast_audio_format = 'none'
    cast_id = -1
    cast_volume = 0
    cast_confirmed = False
    cast_failed_update_count = 0
    max_cast_failed_updates = 20
    cast_nudge_count = 0
    max_cast_nudges = 10

    loop_count = -1

    # Fixed stream details
    cast_url = 'http://%s:8000/' % (gv_server_ip)
    cast_mime_type = 'audio/flac'
    
    while (True):
        if gv_cfg_dict['castMode'] != 'mpd':
            log_message(1, 'Exiting MPD Stream agent (config change)')
            return

        loop_count += 1

        # 1 sec delay per iteration
        time.sleep(1)

        print() # log output separator
        now = int(time.time())

        # Timestamp loop activity for MPD agent
        # acts as a deadlock detection in main loop
        gv_mpd_agent_timestamp = now

        if not mpd_client:
            log_message(
                    1,
                    'Connecting to MPD...')
            try:
                mpd_client = mpd.MPDClient()
                mpd_client.connect('localhost', 6600)
            except:
                log_message(
                        1,
                        'Problem getting mpd client')
                mpd_client = None
                continue

        # Get current MPD status details
        try:
            mpd_client_status = mpd_client.status()
            mpd_client_song = mpd_client.currentsong()

            log_message(
                    gv_verbose,
                    'MPD Status:\n%s' % (
                        json.dumps(
                            mpd_client_status, 
                            indent = 4)))
            log_message(
                    gv_verbose,
                    'MPD Current Song:\n%s' % (
                        json.dumps(
                            mpd_client_song, 
                            indent = 4)))

            mpd_last_status = now

        except:
            # reset... and let next loop reconect
            log_message(
                    1,
                    'Problem getting mpd status')
            mpd_client = None
            mpd_client_status = None
            continue

        # sanity check on status
        # as it can come back empty
        if len(mpd_client_status) == 0:
            log_message(
                    1,
                    'Problem getting mpd status')
            continue

        # mandatory fields
        mpd_status = mpd_client_status['state']

        # optional fields
        if 'volume' in mpd_client_status:
            mpd_volume = int(mpd_client_status['volume'])
        else:
            mpd_volume = -1 # used to track unknown value

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
            # Take first artist if is a list
            if type(artist) == list:
                artist = artist[0]
        if 'album' in mpd_client_song:
            album = mpd_client_song['album']
        if 'title' in mpd_client_song:
            title = mpd_client_song['title']

        # MPD Elapsed time and progress
        mpd_elapsed_mins = int(mpd_elapsed / 60)
        mpd_elapsed_secs = mpd_elapsed % 60
        mpd_duration_mins = int(mpd_duration / 60)
        mpd_duration_secs = mpd_duration % 60
        if mpd_duration > 0:
            mpd_progress = int(mpd_elapsed / mpd_duration * 100)
        else:
            mpd_progress = 0

        if 'audio' in mpd_client_status:
            mpd_audio_format = mpd_client_status['audio']
        else:
            mpd_audio_format = None

        log_message(
                1,
                'Current Track:%s/%s/%s' % (
                    artist,
                    album,
                    title))

        log_message(
                1,
                'MPD (%s) vol:%s %d:%02d/%d:%02d [%02d%%]' % (
                    mpd_status,
                    'N/A' if mpd_volume == -1 else mpd_volume,
                    mpd_elapsed_mins,
                    mpd_elapsed_secs,
                    mpd_duration_mins,
                    mpd_duration_secs,
                    mpd_progress))

        # Cast Device Status
        if (cast_device):

            # We need an updated status from the Cast Device
            # This can fail sometimes when nothing is really wrong and 
            # then other times when things are wrong :)
            #
            # So we give it a tolerance of 20 consecutive failures
            try:
                cast_device.media_controller.update_status()
                # Reset failed status count
                cast_failed_update_count = 0
            except:
                cast_failed_update_count += 1
                log_message(
                        1,
                        'Failed to get cast device status... %d/%d' % (
                            cast_failed_update_count,
                            max_cast_failed_updates))

                if (cast_failed_update_count >= max_cast_failed_updates):
                    log_message(
                            1,
                            'Detected broken controller after %d status failures' % (
                                max_cast_failed_updates))
                    cast_device = None
                    cast_status = 'none'
                    cast_id = -1
                    cast_volume = 0
                    cast_failed_update_count = 0
                    continue

            # Elapsed time as reported by the cast device
            cast_elapsed = int(cast_device.media_controller.status.current_time)
            # Cast player state as reported by the device
            cast_player_state = cast_device.media_controller.status.player_state

            cast_elapsed_mins = int(cast_elapsed / 60)
            cast_elapsed_secs = cast_elapsed % 60

            log_message(
                    1,
                    '%s (%s) [mpd stream] vol:%s %d:%02d' % (
                        cast_name,
                        cast_status,
                        'N/A' if mpd_volume == -1 else cast_volume,
                        cast_elapsed_mins,
                        cast_elapsed_secs))


        # Configured Cast Device change
        # Clear existing device handle
        if (cast_name != gv_cfg_dict['castDevice']):
            # Stop media player of existing device
            # if it exists
            if (cast_device):
                log_message(
                        1,
                        'Detected Cast Device change from %s -> %s' % (
                            cast_name,
                            gv_cfg_dict['castDevice']))
                cast_device.media_controller.stop()
                cast_device.quit_app()
                cast_status = mpd_status
                cast_device = None
                cast_volume = 0
                continue



        # Get cast device when in play state and 
        # no device curently present
        if (mpd_status == 'play' and 
                gv_cfg_dict['castDevice'] != 'Disabled' and 
                not cast_device):
            cast_device = get_cast_device(gv_cfg_dict['castDevice'])

            # nothing to do if this fails
            if not cast_device:
                continue

            cast_name = gv_cfg_dict['castDevice']
            cast_device.wait()
            force_cast = True


        # MPD audio PCM change
        # simply forces a recast
        if (mpd_audio_format and cast_device and 
                mpd_audio_format != cast_audio_format):
            log_message(
                    1,
                    'Forcing recast.. PCM audio change from %s -> %s' % (
                        cast_audio_format, 
                        mpd_audio_format)
                    )
            force_cast = True

            # Also rewind track to start
            # We can lose 1-2 seconds playback otherwise
            mpd_client.seekcur(0)

        # MPD -> Cast Device Events
        # Anything that is driven from detecting changes
        # on the MPD side and pushing to the Cast Device

        # Nothing to do if we don't have a cast
        # device handle
        if (not cast_device):
            continue

        if force_cast:
            # MPD streaming URL
            log_message(
                    1,
                    'casting mpd url:%s type:%s' % (
                        cast_url,
                        cast_mime_type))

            args = {}
            args['content_type'] = cast_mime_type

            # For stream, artwork is a graphic splast with fallback 
            # of platform title
            albumart_url = get_mpd_stream_albumart_url()
            if albumart_url:
                args['thumb'] = albumart_url
                log_message(
                        1,
                        'Stream Albumart URL:%s' % (
                            albumart_url))
            else:
                args['title'] = gv_platform_variant

            # Volume sync before we cast
            if (mpd_volume != -1):
                # Set volume to match local MPD volume
                # avoids sudden volume changes after playback starts when 
                # they sync up
                log_message(
                        1,
                        'Setting Cast Device Volume: %d' % (mpd_volume))
                # Cast Device volume is 0.0 - 1.0 (divide by 100)
                cast_device.set_volume(mpd_volume / 100)
                cast_volume = mpd_volume

            # initiate the cast
            cast_device.media_controller.play_media(
                    cast_url, 
                    **args)
            cast_status = mpd_status
            cast_audio_format = mpd_audio_format
            force_cast = False
            continue

        # Volume change only while playing
        if (cast_status == 'play' and 
                mpd_volume != -1 and 
                cast_volume != mpd_volume):

            log_message(
                    1,
                    'Setting Cast Device Volume: %d' % (mpd_volume))
            # Cast Device volume is 0.0 - 1.0 (divide by 100)
            cast_device.set_volume(mpd_volume / 100)
            cast_volume = mpd_volume
            continue

        # Gentle play nudge on stream
        # if elapsed time is not incrementing
        if (cast_status == 'play' and 
                mpd_status == 'play' and
                cast_elapsed == 0):

            # 5-second grace and we will force a recast
            if cast_nudge_count >= max_cast_nudges:
                log_message(
                        1,
                        'Forcing recast.. max nudge count %d exceeded' % (
                            max_cast_nudges)
                        )
                force_cast = True
                cast_nudge_count = 0
                continue

            # Normal nudge to try and get the stream playing
            cast_nudge_count += 1
            log_message(
                    1,
                    'Nudging cast device to play #%d/%d' % (
                        cast_nudge_count,
                        max_cast_nudges))
            cast_device.media_controller.play()

        # Nudge count reset
        if (cast_status == 'play' and 
                mpd_status == 'play' and
                cast_elapsed > 0):
            cast_nudge_count = 0

        # Pause
        if (cast_status != 'pause' and
            mpd_status == 'pause'):

            log_message(
                    1,
                    'Pausing Cast Device')
            cast_device.media_controller.pause()
            cast_status = mpd_status
            continue
        
        # Resume play
        if (cast_status == 'pause' and 
            mpd_status == 'play'):

            log_message(
                    1,
                    'Unpause Cast Device (recast stream)')
            # force a recast
            force_cast = True
            continue

        # Stop event
        # stop and quit cast app
        if (cast_status != 'stop' and 
            mpd_status == 'stop' and
            cast_device):

            log_message(
                    1,
                    'Stopping Cast App')
            cast_device.media_controller.stop()
            cast_device.quit_app()
            cast_status = mpd_status
            cast_device = None
            cast_volume = 0
            continue  


def mpd_cast_wrapper_agent():
    global gv_cfg_dict

    while (True):

        if gv_cfg_dict['castMode'] == 'direct':
            # MPD File Agent
            log_message(1, 'Starting MPD File Agent')
            mpd_file_agent()
            continue

        if gv_cfg_dict['castMode'] == 'mpd':
            # MPD Stream Agent
            log_message(1, 'Starting MPD Stream Agent')
            mpd_stream_agent()
            continue

        time.sleep(5)

# main()

parser = argparse.ArgumentParser(
        description='MPD Cast Device Agent')

parser.add_argument(
        '--verbose', 
        help = 'Enable verbose output', 
        action = 'store_true')


args = vars(parser.parse_args())
gv_verbose = args['verbose']

# Determine the main IP address of the server
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(('8.8.8.8', 80))
gv_server_ip = s.getsockname()[0]
s.close()

# Determine variant
determine_platform_variant()

# Thread management 
executor = concurrent.futures.ThreadPoolExecutor(
        max_workers = 20)
future_dict = {}

# Config Agent
future_dict['Config Agent'] = executor.submit(
        config_agent)

# Cherry Py web server
future_dict['Web Server'] = executor.submit(
        web_server)

# Cast Device Discovery Agent
future_dict['Cast Device Discovery Agent'] = executor.submit(
        cast_device_discovery_agent)

# MPD Cast Wrapper Agent
future_dict['MPD Cast Wrapper Agent'] = executor.submit(
        mpd_cast_wrapper_agent)

# main loop
while (True):
    exception_dict = {}
    log_message(
            gv_verbose, 
            'threads:%s' % (
                future_dict)
            )

    for key in future_dict:
        future = future_dict[key]
        if future.done():
            if future.exception():
                exception_dict[key] = future.exception()

    if (len(exception_dict) > 0):
        log_message(
                1,
                'Exceptions Detected:\n%s' % (
                    exception_dict)
                )
        os._exit(1) 
    
    # MPD/Cast Device deadlock
    # The MPD loop runs more or less on a 
    # 1-second interval. It will delay and 
    # potentially lock-up if either an MPD or pychromecast
    # call goes bad. This will detect 30 seconds deadlock and exit
    now = int(time.time())
    if (gv_mpd_agent_timestamp > 0 and 
            now - gv_mpd_agent_timestamp >= 30):
        log_message(
                1,
                'Detected deadlocked MPD agent... exiting')
        os._exit(1) 
        
    time.sleep(5)
