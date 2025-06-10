import cv2
import numpy as np
import socket
import time
import os

PIXEL_TO_MM = 12.96
TRUC_X = 270
TRUC_Y = 88
IMG_PATH = r"C:\\Users\\Admin\\OneDrive - Hanoi University of Science and Technology\\Documents\\RPMEC\\Doanxla\\Image_20250610153134245.jpg"
OUT_PATH = "output_detected.jpg"

def detect_objects(image_path, draw_result=True):
    image = cv2.imread(image_path)
    if image is None:
        print("Không đọc được ảnh!")
        return [], (0, 0), None
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    masks = {
        "red":    cv2.inRange(hsv, (0, 100, 100), (10, 255, 255)) | cv2.inRange(hsv, (160, 100, 100), (180, 255, 255)),
        "blue":   cv2.inRange(hsv, (100, 100, 100), (130, 255, 255)),
        "yellow": cv2.inRange(hsv, (20, 100, 100), (35, 255, 255)),
        "green":  cv2.inRange(hsv, (40, 50, 60), (70, 255, 255))
    }
    color_map = {
        "red": (0, 0, 255),
        "blue": (255, 0, 0),
        "yellow": (0, 255, 255),
        "green": (0, 255, 0)
    }
    objects = []
    kernel = np.ones((9, 9), np.uint8)  # Kernel lớn cho closing

    for color, mask in masks.items():
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 5000:
                M = cv2.moments(cnt)
                if M['m00'] == 0: continue
                cx, cy = int(M['m10']/M['m00']), int(M['m01']/M['m00'])
                x, y, w, h = cv2.boundingRect(cnt)
                aspect = w / h if h != 0 else 0

                if 0.9 <= aspect <= 1.1:
                    shape = "square"
                    if area < 50000:
                        detail = "small square"
                    elif area > 80000:
                        detail = "large square"
                    else:
                        detail = "square"
                else:
                    shape = "rectangle"
                    if area < 100000:
                        detail = "small rectangle"
                    elif area > 150000:
                        detail = "large rectangle"
                    else:
                        detail = "rectangle"

                if draw_result:
                    rect = cv2.minAreaRect(cnt)
                    box = cv2.boxPoints(rect)
                    box = box.astype(int)
                    cv2.drawContours(image, [box], 0, color_map[color], 2)
                    label_pos = tuple(box[1])
                    cv2.putText(image, detail, label_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_map[color], 2, cv2.LINE_AA)

                objects.append({
                    "color": color,
                    "pixel": (cx, cy),
                    "area": area,
                    "shape": shape,
                    "detail": detail,
                    "bbox": (x, y, w, h)
                })

    return objects, image.shape, image

class DobotClient:
    def __init__(self, ip="192.168.1.6"):
        self.dash = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.dash.connect((ip, 29999))
        self.motion = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.motion.connect((ip, 30003))

    def send(self, sock, cmd):
        sock.sendall((cmd + '\n').encode())
        return sock.recv(1024).decode()

    def enable_robot(self): return self.send(self.dash, "EnableRobot()")
    def clear_error(self):  return self.send(self.dash, "ClearError()")

    # Có thể truyền speedj, accj từng lệnh
    def movej(self, x, y, z, r, speedj=None, accj=None):
        cmd = f"MovJ({x},{y},{z},{r}"
        if speedj is not None:
            cmd += f",SpeedJ={speedj}"
        if accj is not None:
            cmd += f",AccJ={accj}"
        cmd += ")"
        return self.send(self.motion, cmd)

    # Có thể truyền speedl, accl từng lệnh
    def movel(self, x, y, z, r, speedl=None, accl=None):
        cmd = f"MovL({x},{y},{z},{r}"
        if speedl is not None:
            cmd += f",SpeedL={speedl}"
        if accl is not None:
            cmd += f",AccL={accl}"
        cmd += ")"
        return self.send(self.motion, cmd)

    def close(self): self.dash.close(); self.motion.close()

def pixel_to_robot(pixel, img_shape):
    px, py = pixel
    X = px / PIXEL_TO_MM + TRUC_X
    Y = TRUC_Y - py / PIXEL_TO_MM
    Z = -140
    R = 0
    return X, Y, Z, R

def main():
    objects, img_shape, image_with_boxes = detect_objects(IMG_PATH, draw_result=True)
    if not objects:
        print("Không tìm thấy vật thể nào!")
        return

    cv2.imwrite(OUT_PATH, image_with_boxes)
    print(f"Đã lưu ảnh kết quả vào {OUT_PATH}")

    for i, obj in enumerate(objects, 1):
        print(f"#{i}: {obj['color']} tại pixel {obj['pixel']} diện tích {obj['area']:.1f} loại {obj['detail']}")

    robot = DobotClient()
    print("Enable robot:", robot.enable_robot())
    time.sleep(0.5)
    print("Clear error:", robot.clear_error())
    time.sleep(0.2)

    for i, obj in enumerate(objects, 1):
        x, y, z, r = pixel_to_robot(obj['pixel'], img_shape)
        print(f"({i}) Robot đi tới {obj['color']} ({x:.1f}, {y:.1f}, {z:.1f}, {r:.1f})")
        # Di chuyển về vị trí trung gian (nhanh)
        robot.movej(400, -15, 0, 0, speedj=50, accj=60)
        # Đến trên vật thể (chậm, chính xác)
        robot.movej(x, y, z+50, r, speedj=25, accj=30)
        robot.send(robot.motion, "DO(5,0)")
        robot.movel(x, y, z, r, speedl=10, accl=15)
        time.sleep(1)
        robot.send(robot.motion, "DO(1,1)")
        time.sleep(1)
        robot.movel(x, y, z+50, r, speedl=10, accl=25)
        time.sleep(0.5)

        # Phân loại điểm đặt, có thể set lại speed/acc cho từng đối tượng nếu muốn!
        # phân biệt màu đỏ
        if obj['color'] == "red" and obj['detail'] == "small square":
            robot.movej(276, -210, -50, 0, speedj=30, accj=15)
            time.sleep(1)
            robot.send(robot.motion, "DO(1,0)")
            robot.send(robot.motion, "DO(5,1)")
        elif obj['color'] == "red" and obj['detail'] == "large square":
            robot.movej(276, -210, -50, 0, speedj=30, accj=15)
            time.sleep(1)
            robot.send(robot.motion, "DO(1,0)")
            robot.send(robot.motion, "DO(5,1)")
        elif obj['color'] == "red" and obj['detail'] == "small rectangle":
            robot.movej(350, -130, 0, 0, speedj=40, accj=50)
            robot.send(robot.motion, "DO(1,0)")
            robot.send(robot.motion, "DO(5,1)")
        elif obj['color'] == "red" and obj['detail'] == "large rectangle":
            robot.movej(350, -110, 0, 0, speedj=40, accj=50)
            robot.send(robot.motion, "DO(1,0)")
            robot.send(robot.motion, "DO(5,1)")
        # phân biệt màu xanh dương
        elif obj['color'] == "blue" and obj['detail'] == "small square":
            robot.movej(350, 162, 0, 0, speedj=40, accj=50)
            robot.send(robot.motion, "DO(1,0)")
            robot.send(robot.motion, "DO(5,1)")
        elif obj['color'] == "blue" and obj['detail'] == "large square":
            robot.movej(255, 210, 0, 0, speedj=30, accj=15)
            time.sleep(1)
            robot.send(robot.motion, "DO(1,0)")
            robot.send(robot.motion, "DO(5,1)")
        elif obj['color'] == "blue" and obj['detail'] == "small rectangle":
            robot.movej(350, 122, 0, 0, speedj=40, accj=50)
            robot.send(robot.motion, "DO(1,0)")
            robot.send(robot.motion, "DO(5,1)")
        elif obj['color'] == "blue" and obj['detail'] == "large rectangle":
            robot.movej(350, 102, 0, 0, speedj=40, accj=50)
            robot.send(robot.motion, "DO(1,0)")
            robot.send(robot.motion, "DO(5,1)")
        # phân biệt màu vàng
        elif obj['color'] == "yellow" and obj['detail'] == "small square":
            robot.movej(300, 50, 0, 0, speedj=40, accj=50)
            robot.send(robot.motion, "DO(1,0)")
            robot.send(robot.motion, "DO(5,1)")
        elif obj['color'] == "yellow" and obj['detail'] == "large square":
            robot.movej(367, 160, -30, 0, speedj=30, accj=15)
            time.sleep(1)
            robot.send(robot.motion, "DO(1,0)")
            robot.send(robot.motion, "DO(5,1)")
        elif obj['color'] == "yellow" and obj['detail'] == "small rectangle":
            robot.movej(300, 90, 0, 0, speedj=40, accj=50)
            robot.send(robot.motion, "DO(1,0)")
            robot.send(robot.motion, "DO(5,1)")
        elif obj['color'] == "yellow" and obj['detail'] == "large rectangle":
            robot.movej(300, 110, 0, 0, speedj=40, accj=50)
            robot.send(robot.motion, "DO(1,0)")
            robot.send(robot.motion, "DO(5,1)")
        # phan biet mau xanh la cay   
        elif obj['color'] == "green" and obj['detail'] == "small square":
            robot.movej(300, 130, 0, 0, speedj=40, accj=50)
            robot.send(robot.motion, "DO(1,0)")
            robot.send(robot.motion, "DO(5,1)")
        elif obj['color'] == "green" and obj['detail'] == "large square":
            robot.movej(353, -181, -30, 0, speedj=30, accj=15)
            time.sleep(1)
            robot.send(robot.motion, "DO(1,0)")
            robot.send(robot.motion, "DO(5,1)")
        elif obj['color'] == "green" and obj['detail'] == "small rectangle":
            robot.movej(300, 170, 0, 0, speedj=40, accj=50)
            robot.send(robot.motion, "DO(1,0)")
            robot.send(robot.motion, "DO(5,1)")
        elif obj['color'] == "green" and obj['detail'] == "large rectangle":
            robot.movej(300, 190, 0, 0, speedj=40, accj=50)
            robot.send(robot.motion, "DO(1,0)")
            robot.send(robot.motion, "DO(5,1)")
        else:
            print("Không xác định màu hoặc loại vật thể!")
    time.sleep(0.5)
    robot.movej(400, -15, 0, 0, speedj=60, accj=60)
    robot.send(robot.motion, "DO(5,0)")
    robot.close()
    print("Đã hoàn thành nhặt tất cả vật thể.")

if __name__ == "__main__":
    main()
