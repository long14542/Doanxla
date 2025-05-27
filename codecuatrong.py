import cv2
import numpy as np
import socket
import time

# 1. Đếm số lượng vật thể trên ảnh (theo mask đỏ/xanh dương)
def count_objects(image_path, debug=False):
    image = cv2.imread(image_path)
    if image is None:
        print("Không đọc được ảnh!")
        return 0, [], (0, 0)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    lower_red1 = np.array([0, 100, 100])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([160, 100, 100])
    upper_red2 = np.array([180, 255, 255])
    lower_blue = np.array([100, 100, 100])
    upper_blue = np.array([130, 255, 255])

    mask_red = cv2.inRange(hsv, lower_red1, upper_red1) | cv2.inRange(hsv, lower_red2, upper_red2)
    mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)

    if debug:
        cv2.imshow("Red mask", mask_red)
        cv2.imshow("Blue mask", mask_blue)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    objects = []
    for color, mask in [("red", mask_red), ("blue", mask_blue)]:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 100:
                M = cv2.moments(cnt)
                if M['m00'] != 0:
                    cx = int(M['m10'] / M['m00'])
                    cy = int(M['m01'] / M['m00'])
                    objects.append({
                        "color": color,
                        "pixel": (cx, cy),
                        "area": area
                    })
    return len(objects), objects, image.shape

# 2. Kết nối robot MG400
class DobotClient:
    def __init__(self, ip="192.168.1.6"):
        self.dash_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.dash_sock.connect((ip, 29999))
        self.motion_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.motion_sock.connect((ip, 30003))

    def send_dashboard(self, cmd):
        self.dash_sock.sendall((cmd + '\n').encode())
        return self.dash_sock.recv(1024).decode()

    def send_motion(self, cmd):
        self.motion_sock.sendall((cmd + '\n').encode())
        return self.motion_sock.recv(1024).decode()

    def enable_robot(self):
        return self.send_dashboard("EnableRobot()")

    def clear_error(self):
        return self.send_dashboard("ClearError()")

    def movl(self, x, y, z, r):
        return self.send_motion(f"MovL({x},{y},{z},{r})")

    def close(self):
        self.dash_sock.close()
        self.motion_sock.close()

# 3. Chuyển đổi pixel sang tọa độ robot
def pixel_to_robot(pixel, image_shape):
    px, py = pixel
    img_h, img_w = image_shape[:2]
    X = 200 + (px / img_w) * (400 - 200)
    Y = -200 + (py / img_h) * 200
    Z = 50
    R = 0
    return (X, Y, Z, R)

# 4. Main
def main():
    # === NHẬP ẢNH TRỰC TIẾP TỪ ĐƯỜNG DẪN ===
    image_path = "abcdef.jpg"  # <-- Cập nhật đường dẫn ảnh tại đây

    print("Đang đếm số lượng vật thể ...")
    num_obj, objects, image_shape = count_objects(image_path, debug=False)
    print(f"Số lượng vật thể phát hiện được: {num_obj}")

    if num_obj == 0:
        print("Không tìm thấy vật thể phù hợp trên ảnh!")
        return

    for i, obj in enumerate(objects):
        print(f"#{i+1}: {obj['color']} tại pixel {obj['pixel']} diện tích {obj['area']}")

    robot = DobotClient(ip="192.168.1.6")
    print("Enable robot:", robot.enable_robot())
    time.sleep(0.5)
    print("Clear error:", robot.clear_error())
    time.sleep(0.2)

    for idx, obj in enumerate(objects):
        x, y, z, r = pixel_to_robot(obj['pixel'], image_shape)
        print(f"({idx+1}) Robot đi đến {obj['color']} tại ({x:.1f}, {y:.1f}, {z:.1f}, {r:.1f})")
        result = robot.movl(x, y, z, r)
        print("Kết quả MovL:", result)
        time.sleep(0.5)

    robot.close()
    print("Hoàn thành nhặt tất cả vật thể.")

if __name__ == "__main__":
    main()