from __future__ import print_function, division
import numpy as np
import sys
import cv2
import pyaudio
import wave
import threading
import time
import os
import ffmpeg

import speech_recognition as sr 
from pydub import AudioSegment
from pydub.silence import split_on_silence
import subprocess
import time

class SpeechToText:
    @staticmethod
    def get_transcription(path):
        sound = AudioSegment.from_wav(path)
        chunks = split_on_silence(sound,
            min_silence_len = 500,
            silence_thresh = sound.dBFS-14,
            keep_silence=500,
        )
        folder_name = "audio-chunks"
        if not os.path.isdir(folder_name):
            os.mkdir(folder_name)
        whole_text = ""
        for i, audio_chunk in enumerate(chunks, start=1):
            chunk_filename = os.path.join(folder_name, f"chunk{i}.wav")
            audio_chunk.export(chunk_filename, format="wav")
            # recognize the chunk
            with sr.AudioFile(chunk_filename) as source:
                audio_listened = r.record(source)
                try:
                    text = r.recognize_google(audio_listened)
                except sr.UnknownValueError as e:
                    print("Error:", e)
                else:
                    text = f"{text.capitalize()}. "
                    whole_text += text
        return whole_text


REC_FOLDER = "recordings/"

class Recorder():
    def __init__(self, filename):
        self.filename = filename
        self.video_thread = self.VideoRecorder(self, REC_FOLDER + filename)
        self.audio_thread = self.AudioRecorder(self, REC_FOLDER + filename)

    def startRecording(self):
        self.video_thread.start()
        self.audio_thread.start()

    def stopRecording(self):
        self.video_thread.stop()
        self.audio_thread.stop()

    def saveRecording(self):
        # Save audio / Show video resume
        self.audio_thread.saveAudio()
        self.video_thread.showFramesResume()

        # Merges both streams and writes
        video_stream = ffmpeg.input(self.video_thread.video_filename)
        audio_stream = ffmpeg.input(self.audio_thread.audio_filename)
        while (not os.path.exists(self.audio_thread.audio_filename)):
            print("waiting for audio file to exit...")
        stream = ffmpeg.output(video_stream, audio_stream,
                               REC_FOLDER + self.filename + ".mp4")

        try:
            ffmpeg.run(stream, capture_stdout=True,
                       capture_stderr=True, overwrite_output=True)
        except ffmpeg.Error as e:
            print(e.stdout, file=sys.stderr)
            print(e.stderr, file=sys.stderr)

    class VideoRecorder():
        "Video class based on openCV"

        def __init__(self, recorder, name, fourcc="MJPG", frameSize=(640, 480), camindex=1, fps=15):
            self.recorder = recorder
            self.open = True
            self.duration = 0
            self.device_index = camindex
            # fps should be the minimum constant rate at which the camera can
            self.fps = fps
            # capture images (with no decrease in speed over time; testing is required)
            self.fourcc = fourcc
            # video formats and sizes also depend and vary according to the camera used
            self.video_filename = f"{name}.avi"
            self.video_cap = cv2.VideoCapture(self.device_index, cv2.CAP_DSHOW)
            self.video_writer = cv2.VideoWriter_fourcc(*fourcc)
            self.video_out = cv2.VideoWriter(
                self.video_filename, self.video_writer, self.fps, frameSize)
            self.frame_counts = 1
            self.start_time = time.time()

        def record(self):
            "Video starts being recorded"
            counter = 1
            print ("Inside the Video recording thread")
            while self.open:
                ret, video_frame = self.video_cap.read()
                if not ret:
                    break

                self.video_out.write(video_frame)
                self.frame_counts += 1
                counter += 1
                self.duration += 1/self.fps
                if (video_frame is None):
                    print("Video frame is none")
                cv2.imshow('video_frame', video_frame)
                cv2.waitKey(1)

                while (self.duration - self.recorder.audio_thread.duration >= 0.2 and self.recorder.audio_thread.open):
                    time.sleep(0.2)
            # Release Video
            self.video_out.release()
            self.video_cap.release()
            cv2.destroyAllWindows()
            self.video_out = None

        def stop(self):
            print("Finishes the video recording therefore the thread too")
            self.open = False

        def start(self):
            print("Launches the video recording function using a thread")
            self.thread = threading.Thread(target=self.record)
            self.thread.start()

        def showFramesResume(self):
            # Only stop of video has all frames
            frame_counts = self.frame_counts
            elapsed_time = time.time() - self.start_time
            recorded_fps = self.frame_counts / elapsed_time
            print(f"total frames {str(frame_counts)}")
            print(f"elapsed time {str(elapsed_time)}")
            print(f"recorded fps {str(recorded_fps)}")

    class AudioRecorder():
        print("Audio class based on pyAudio and Wave")

        def __init__(self, recorder, filename, rate=44100, fpb=1024, channels=1, audio_index=0):
            self.recorder = recorder
            self.open = True
            self.rate = rate
            self.duration = 0
            self.frames_per_buffer = fpb
            self.channels = channels
            self.format = pyaudio.paInt16
            self.audio_filename = f"{filename}.wav"
            self.audio = pyaudio.PyAudio()
            self.stream = self.audio.open(format=self.format,
                                          channels=self.channels,
                                          rate=self.rate,
                                          input=True,
                                          input_device_index=audio_index,
                                          frames_per_buffer=self.frames_per_buffer)
            self.audio_frames = []

        def record(self):
            "Audio starts being recorded"
            print ("Inside the Audio recording thread")
            self.stream.start_stream()
            t_start = time.time_ns()
            while self.open:
                try:
                    self.duration += self.frames_per_buffer / self.rate
                    data = self.stream.read(self.frames_per_buffer)
                    self.audio_frames.append(data)
                except Exception as e:
                    print('\n' + '*'*80)
                    print('PyAudio read exception at %.1fms\n' %
                          ((time.time_ns() - t_start)/10**6))
                    print(e)
                    print('*'*80 + '\n')
                while (self.duration - self.recorder.video_thread.duration >= 0.5):
                    time.sleep(0.5)
            # Closes audio stream
            self.stream.stop_stream()
            self.stream.close()
            self.audio.terminate()

        def stop(self):
            print("Finishes the audio recording therefore the thread too")
            self.open = False

        def start(self):
            print("Launches the audio recording function using a thread")
            self.thread = threading.Thread(target=self.record)
            self.thread.start()

        def saveAudio(self):
            print("Save Audio File")
            waveFile = wave.open(self.audio_filename, 'wb')
            waveFile.setnchannels(self.channels)
            waveFile.setsampwidth(self.audio.get_sample_size(self.format))
            waveFile.setframerate(self.rate)
            waveFile.writeframes(b''.join(self.audio_frames))
            waveFile.close()

filename = "sampleDemo"
recorder = Recorder(filename)
recorder.startRecording()
mode = input("Press E to Escape: ")
if mode == 'E':
    recorder.stopRecording()
    recorder.saveRecording()

    r = sr.Recognizer()
    path = f"recordings/{filename}.wav"
    print ("Converting audio to txt")
    start_time = time.time()
    text = SpeechToText.get_transcription(path)
    with open(f"{filename}.txt","w") as fi:
        fi.write(text)

    print(f"Transcribed text is saved to {filename}.txt")
    print(f"--- {time.time() - start_time} seconds ---")