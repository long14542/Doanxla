#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mg400_control.py — Xử lý ảnh + điều khiển MG400, tự động tắt GUI nếu thiếu HighGUI.
"""

import cv2
import numpy as np
import socket
import sys
import time

# === 1. Cấu hình mạng & robot ===
HOST = '192.168.1.6'
PORT_DASH = 29999
PORT_MOT  = 30003
SOCKET_TIMEOUT = 5

# === 2. Tạo kết nối với Dobot ===
def make_socket(name, host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(SOCKET_TIMEOUT)
    try:
        sock.connect((host, port))
        print(f"[OK] {name} connected @ {host}:{port}")
        return sock
    except Exception as e:
        print(f"[ERROR] {name} connect failed: {e}")
        sys.exit(1)

dash = make_socket('Dashboard', HOST, PORT_DASH)
mot  = make_socket('Motion',    HOST, PORT_MOT)

def send_command(sock, cmd, wait_resp=True):
    try:
        sock.sendall((cmd + '\n').encode())
        if wait_resp:
            return sock.recv(1024).decode().strip()
    except Exception as e:
        print(f"[ERROR] send_command: {e}")
        sys.exit(1)
    return None

send_command(dash, 'EnableRobot(0.5,0,0,5.5)')

# === 3. Ánh xạ pixel -> tọa độ robot ===
def pixel_to_robot(cx, cy):
    X = cx * 0.5 + 100
    Y = cy * -0.5 + 200
    Z = 50
    return X, Y, Z

# === 4. Chuẩn bị camera ===
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("[ERROR] Không mở được camera.")
    sys.exit(1)

# thử tạo cửa sổ, nếu lỗi thì headless
headless = False
try:
    cv2.namedWindow("MG400 View")
except cv2.error:
    headless = True
    print("[WARN] GUI không khả dụng, chạy chế độ headless.")

COLOR_RANGES = {
    'red':  ((0,100,100), (10,255,255)),
    'blue': ((100,150,0), (140,255,255)),
}
TRAYS = {
    'red':  (150,  50, 50),
    'blue': (150, 150, 50),
}

print("=== Bắt đầu xử lý (ESC để thoát) ===")
while True:
    ret, frame = cap.read()
    if not ret:
        break

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    for color, (lo, hi) in COLOR_RANGES.items():
        mask = cv2.inRange(hsv, np.array(lo), np.array(hi))
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in cnts:
            if cv2.contourArea(cnt) < 500: continue

            approx = cv2.approxPolyDP(cnt, 0.04*cv2.arcLength(cnt,True), True)
            shape = ('circle' if len(approx)>8 else
                     'triangle' if len(approx)==3 else
                     'square')

            M = cv2.moments(cnt)
            if M['m00']==0: continue
            cx = int(M['m10']/M['m00'])
            cy = int(M['m01']/M['m00'])

            if not headless:
                cv2.drawContours(frame, [cnt], -1, (0,0,0), 2)
                cv2.putText(frame, f"{color}_{shape}", (cx-30,cy-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0),1)

            # Dobot thao tác
            X,Y,Z = pixel_to_robot(cx,cy)
            send_command(mot, f"MovL({X},{Y},{Z+50},0,SpeedL=100,AccL=100)")
            send_command(mot, f"MovL({X},{Y},{Z},0,SpeedL=50,AccL=50)")
            send_command(mot, "DO(1,1)"); time.sleep(0.5)
            tx,ty,tz = TRAYS[color]
            send_command(mot, f"MovL({X},{Y},{Z+50},0,SpeedL=100,AccL=100)")
            send_command(mot, f"MovL({tx},{ty},{tz},0,SpeedL=50,AccL=50)")
            send_command(mot, "DO(1,0)"); send_command(mot, "Sync()")

    if not headless:
        cv2.imshow("MG400 View", frame)
        if cv2.waitKey(1)&0xFF==27:
            break

# cleanup
cap.release()
if not headless:
    cv2.destroyAllWindows()
send_command(dash, 'DisableRobot()')
dash.close(); mot.close()
print("=== Kết thúc chương trình ===")
