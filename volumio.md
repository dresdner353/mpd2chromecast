## Installation on Volumio platforms

**Note:** This set of steps was orginally working with standard Volumio releases. Alas, Volumio is still based on Raspian Jesse and it's just too old to keep up with working versions of pychromecast, Python3 and other dependencies. So the installation here only really works on beta Volumio images based on Raspian Buster. I had tried all kinds of approaches to recompiling later Python releases on the Jesse stack and just kept hitting one issue after the other. The beta images is by no means perfect and I've seen a few funny behaviours here and there with it. So at this stage, you may need to wait for Volumio devs to get a Buster image available with Volumio if you are expecting more stability.

Download the Buster beta image:
https://community.volumio.org/t/volumio-debian-buster-beta-raspi-images-debugging/11988

Usual flash process applies for the install.

After instalation, browse to http://volumio.local/dev and enable the SSH option. Then ssh into the box as volumio@volumio.local, password "volumio" and follow the commands below..

Update package lists and install the related Python3 components:
```
sudo apt-get update
sudo apt-get install python3-pip
sudo pip3 install pychromecast cherrypy python-mpd2
```

Install the script as follows:
```
cd
git clone https://github.com/dresdner353/mpd2chromecast.git
```

Continue the setup and testing [here](./README.md#selecting-desired-chromecast). 
