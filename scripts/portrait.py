"""Feathered face brightening for a visually confirmed on-camera speaker."""

from pathlib import Path
import subprocess

import cv2
import numpy as np


def detect_track(source, item):
    capture = cv2.VideoCapture(str(source))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS)
    detector = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    center = item.get('speaker_x', .5) * width
    top, bottom = item.get('face_roi', [.15, .65])
    times, boxes = [], []
    index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if index % 3 == 0:
            y0, y1 = round(height * top), round(height * bottom)
            region = cv2.cvtColor(frame[y0:y1], cv2.COLOR_BGR2GRAY)
            found = detector.detectMultiScale(cv2.equalizeHist(region), 1.1, 5, minSize=(36, 36))
            candidates = [box for box in found if abs(box[0] + box[2]/2 - center) < width * .24]
            if candidates:
                x, y, w, h = min(candidates, key=lambda box: abs(box[0]+box[2]/2-center) - .22*box[2])
                times.append(index)
                boxes.append([x+w/2, y+y0+h/2, w, h])
        index += 1
    capture.release()
    warnings = []
    if len(times) < 5 or len(times) / max(1, (index+2)//3) < .4:
        return width, height, fps, [None] * index, ['人脸跟踪不足，跳过局部提亮，需复核主讲人位置']
    frames = np.arange(index)
    track = np.column_stack([np.interp(frames, times, column) for column in np.array(boxes).T])
    smoothed = [np.median(track[max(0,i-3):i+4], axis=0) for i in range(index)]
    if max(np.diff(times), default=0) > fps:
        warnings.append('人脸检测有超过一秒的缺口，相应帧跳过局部提亮，需检查衔接')
    # Avoid projecting a stale face box over a long occlusion or another subject.
    distance = np.minimum(
        np.abs(frames - np.array(times)[np.clip(np.searchsorted(times, frames), 0, len(times)-1)]),
        np.abs(frames - np.array(times)[np.clip(np.searchsorted(times, frames)-1, 0, len(times)-1)]),
    )
    return width, height, fps, [box if distance[i] <= fps*.5 else None
                                for i, box in enumerate(smoothed)], warnings


def grade(frame, box, overall, face):
    level = np.linspace(0, 1, 256, dtype=np.float32)
    curve = np.clip(np.rint((level + overall*np.sin(np.pi*level))*255), 0, 255).astype(np.uint8)
    result = cv2.LUT(frame, curve)
    if box is None or not face:
        return result
    height, width = frame.shape[:2]
    cx, cy, w, h = box
    left, right = max(0, int(cx-w*.7)), min(width, int(cx+w*.7+1))
    top, bottom = max(0, int(cy-h*.79)), min(height, int(cy+h*.79+1))
    yy, xx = np.ogrid[top:bottom, left:right]
    distance = np.sqrt(((xx-cx)/(w*.54))**2 + ((yy-cy)/(h*.65))**2)
    feather = np.clip((1.16-distance)/.53, 0, 1).astype(np.float32)
    patch = result[top:bottom, left:right]
    lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB).astype(np.float32)
    lab[:, :, 0] += feather*face*np.sin(np.pi*lab[:, :, 0]/255)
    lab[:, :, 1:] = 128 + (lab[:, :, 1:]-128)*(1-.065*feather[:, :, None])
    result[top:bottom, left:right] = cv2.cvtColor(
        np.clip(np.rint(lab), 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)
    return result


def render_grade(source, folder, item):
    if item.get('face', 0):
        width, height, fps, track, warnings = detect_track(source, item)
    else:
        capture = cv2.VideoCapture(str(source))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = capture.get(cv2.CAP_PROP_FPS)
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        capture.release()
        track, warnings = [None]*count, []
    destination = Path(folder) / 'graded.mp4'
    capture = cv2.VideoCapture(str(source))
    command = ['ffmpeg', '-y', '-v', 'error', '-f', 'rawvideo', '-pixel_format', 'bgr24',
               '-video_size', f'{width}x{height}', '-framerate', str(fps), '-i', 'pipe:0',
               '-i', str(source), '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libx264',
               '-preset', 'fast', '-crf', '17', '-pix_fmt', 'yuv420p', '-c:a', 'copy', str(destination)]
    try:
        with subprocess.Popen(command, stdin=subprocess.PIPE) as encoder:
            try:
                for box in track:
                    ok, frame = capture.read()
                    if not ok:
                        raise RuntimeError('Frame read failed while grading')
                    updated = grade(frame, box, item.get('overall', 0), item.get('face', 0))
                    encoder.stdin.write(updated.tobytes())
            finally:
                encoder.stdin.close()
            if encoder.wait():
                raise RuntimeError('Face-brightening encoder failed')
    finally:
        capture.release()
    return destination, warnings
