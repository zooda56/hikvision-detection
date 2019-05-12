import configparser
import datetime
import os
import time
import xml.etree.ElementTree as ET
from shutil import copyfile
import requests
from requests.auth import HTTPDigestAuth
from subprocess import Popen

print("Hikvision alert started")

# CONFIGS START
config = configparser.ConfigParser()
exists = os.path.isfile('/config/config.ini')

if exists:
    config.read('/config/config.ini')
else:
    copyfile('cfg/config.ini', '/config/config.ini')
    config.read('/config/config.ini')

APP_PATH = config['DEFAULT']['APP_PATH']
NVR_URL = config['DEFAULT']['NVR_URL']
NVR_USR = config['DEFAULT']['NVR_USR']
NVR_PASS = config['DEFAULT']['NVR_PASS']
# CONFIGS ENDS

XML_NAMESPACE = 'http://www.hikvision.com/ver20/XMLSchema'

DEFAULT_HEADERS = {
    'Content-Type': "application/xml; charset='UTF-8'",
    'Accept': "*/*"
}

hik_request = requests.Session()
hik_request.auth = HTTPDigestAuth(NVR_USR, NVR_PASS)
hik_request.headers.update(DEFAULT_HEADERS)

url = NVR_URL + '/ISAPI/Event/notification/alertStream'

parse_string = ''
start_event = False
fail_count = 0

detection_date = datetime.datetime.now()
detection_id = '0'

while True:

    try:
        stream = hik_request.get(url, stream=True, timeout=(5, 60))

        if stream.status_code != requests.codes.ok:
            raise ValueError('Connection unsuccessful.')
        else:
            print('Connection successful to: ' + NVR_URL)
            fail_count = 0

        for line in stream.iter_lines():
            # filter out keep-alive new lines
            if line:
                str_line = line.decode("utf-8")

                if str_line.find('<EventNotificationAlert') != -1:
                    start_event = True
                    parse_string += str_line
                elif str_line.find('</EventNotificationAlert>') != -1:
                    parse_string += str_line
                    start_event = False
                    if parse_string:
                        tree = ET.fromstring(parse_string)

                        channelID = tree.find('{%s}%s' % (XML_NAMESPACE, 'channelID'))
                        if channelID is None:
                            # Some devices use a different key
                            channelID = tree.find('{%s}%s' % (XML_NAMESPACE, 'dynChannelID'))

                        if channelID.text == '0':
                            # Continue and clear the chunk
                            parse_string = ""
                            continue

                        eventType = tree.find('{%s}%s' % (XML_NAMESPACE, 'eventType'))
                        eventState = tree.find('{%s}%s' % (XML_NAMESPACE, 'eventState'))
                        postCount = tree.find('{%s}%s' % (XML_NAMESPACE, 'activePostCount'))

                        current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        print('%s - count: %s event: %s eventState: %s channel_id: %s ' % (
                            current_date, postCount.text, eventType.text, eventState.text,
                            channelID.text))
                        if eventType.text == 'linedetection':
                            # Only trigger the event if the event not repeated in 5 sec
                            if (detection_date < datetime.datetime.now() - datetime.timedelta(
                                    seconds=5)) and (detection_id != channelID):
                                print('%s - count: %s event: %s eventState: %s channel_id: %s ' % (
                                    current_date, postCount.text, eventType.text, eventState.text,
                                    channelID.text))
                                detection_date = datetime.datetime.now()
                                detection_id = channelID.text
                                # start the subprocess to process by channelID
                                p = Popen('python ' + APP_PATH + '/image_process.py ' + channelID.text,
                                          shell=True)

                        # Clear the chunk
                        parse_string = ""

                else:
                    if start_event:
                        parse_string += str_line

    except (ValueError, requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as err:
        fail_count += 1
        time.sleep(fail_count * 5)
        continue
