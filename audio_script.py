# This is HEAVILY based on this script by Zolmeister
# https://github.com/Zolmeister/AudioMan/blob/master/audioman.py
# I have modified it to work with my Tuya WiFi Smart Bulb
# and added a function to cause the light to go rainbow colors as well
# To pull this off with the bulb, I also needed to add a delay to all
# functions and implement a command queue so that it can respond to 
# all commands w/o overloading.


import pyaudio
import wave
import time
import struct
import math
import tinytuya

import queue
import threading
import logging
import json

import os

#serr=serial.Serial('/dev/ttyACM0',115200)
chunk = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
RECORD_SECONDS = 500000
WAVE_OUTPUT_FILENAME = "output.wav"

config = {}

with open("config.json") as f:
    config = json.load(f)

DEVICEID = config["deviceid"]
DEVICEIP = config["deviceip"]
DEVICEKEY = config["devicekey"]
DEVICEVERS = config["devicevers"]
DELAY = 1

DELAY = os.getenv("DELAY", DELAY)

#dict of commands
q = queue.Queue()

d = tinytuya.BulbDevice(DEVICEID, DEVICEIP, DEVICEKEY)
d.set_version(float(DEVICEVERS))  # IMPORTANT to always set version
# Keep socket connection open between commands
d.set_socketPersistent(True)

p = pyaudio.PyAudio()

stream = p.open(format = FORMAT,
                channels = CHANNELS,
                rate = RATE,
                input = True,
                output = False,
                frames_per_buffer = chunk)

def sendVal(r):
	global maxNormal
	global prev
	global prevVals
	global serr
	r=float(r)
	maxNormal=float(maxNormal)
	if r>maxNormal:
		maxNormal=r
	normalized=r/maxNormal*255
	normalized=int(normalized)
	prevVals.append(normalized)
	while len(prevVals)>=100:
		prevVals=prevVals[1:]
		if sum(prevVals)*1.0/len(prevVals)<=10:
			minNormal=1
			maxNormal=1
	norm=(normalized+prev)/2
    # We were having errors with negatives, normalize this
	#if norm < 0:
#		norm = 0
    #Original code normalized it around 255. Rather than adjusting this
    #divide by 255 to create a percentage and multiply by 100
    #to give us a percentage from 0-100
	q.put(('brightness', (norm/255)*100))
	prev=normalized

def command_queue():
    #Command interpreter
    #Basically this just wraps the original commands for the bulb 
    #into a form that can be queued
    while True:
        #print("checking for commands")
        if q.qsize() > 0:
            command = q.get()
            if command[0] == 'color':
                #print('sending: color')
                d.set_colour(command[1][0], command[1][1], command[1][2])
            elif command[0] == 'brightness':
                #print("sending brightness")
                d.set_brightness_percentage(command[1])
        #The light bulb has a delay in how often it can process commands
        #Handle that here in the queue
        time.sleep(0.01*DELAY)


def rainbow_thread():
    rainbow = {"red": [255, 0, 0], "orange": [255, 127, 0], "yellow": [255, 200, 0],
            "green": [0, 255, 0], "blue": [0, 0, 255], "indigo": [46, 43, 95],
            "violet": [139, 0, 255]}
    #Very simple loop that just adds a color to the queue every second times whatever
    #delay you have set
    while (True):
        for color in rainbow:
            #print("enquing color")
            q.put(("color", rainbow[color]))
            time.sleep(1*DELAY)

#Most of this is from the original script and includes the audio processing
def audio_thread():
    global all
    for i in range(0, int(RATE / chunk * RECORD_SECONDS)):
        try:
            data = stream.read(chunk)
        except:
            continue
        #WHY WAS THIS BEING DONE? WRITING BACK TO THE OUTPUT STREAM CORRUPTS IT!
        #stream.write(data, chunk)
        all.append(data)
        if len(all)>1:
            data = b''.join(all)
            wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(p.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(data)
            wf.close()
            w = wave.open(WAVE_OUTPUT_FILENAME, 'rb')
            summ = 0
            value = 1
            delta = 1
            amps = [ ]
            for i in range(0, w.getnframes()):
                data = struct.unpack('<h', w.readframes(1))
                summ += (data[0]*data[0]) / 2
                if (i != 0 and (i % 1470) == 0):
                    value = int(math.sqrt(summ / 1470.0) / 10)
                    amps.append(value - delta)                
                    summ = 0
                    tarW=str(amps[0]*1.0/delta/100)
                    #ser.write(tarW)
                    sendVal(tarW)
                    delta = value
            all=[]
            time.sleep(0.2*DELAY)
    print("this should never print")

def main():
    #Rainbow thread is a daemon so that it gets killed at end of function
    r_thread = threading.Thread(target=rainbow_thread, daemon=True)
    a_thread = threading.Thread(target=audio_thread)
    c_thread = threading.Thread(target=command_queue, daemon=True)
    print("starting audio thread")
    a_thread.start()
    print("starting rainbow thread")
    r_thread.start()
    print("starting command thread")
    c_thread.start()
    print("waiting for completion of audio thread")
    #a_thread.join()


if __name__ == '__main__':
    try:
        print("* recording")
        maxNormal = 1
        prevVals = [0, 255]
        prev = 0
        all = []
        main()
    except KeyboardInterrupt:
        stream.close()
        p.terminate()
        d.set_mode('white')
        d.turn_off()
        d.close()
