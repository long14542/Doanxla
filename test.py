import cv2
import numpy as np
import socket
import time
import os
import math

# --- CÁC THAM SỐ HIỆU CHỈNH VÀ ĐƯỜNG DẪN ---
PIXEL_TO_MM = 12.96
TRUC_X = 270
TRUC_Y = 88
# Thay đổi đường dẫn này đến ảnh bạn muốn kiểm tra
# Ví dụ: r"C:\path\to\your\image.jpg"
IMG_PATH = r"C:\Users\admin\MVS\Data\Image_20250610155347307.bmp"
OUT_PATH = "output_detected_final.jpg"
DEBUG_INITIAL_MASK_PATH = "debug_initial_mask.jpg"
DEBUG_ERODED_MASK_PATH = "debug_eroded_mask.jpg"


def calculate_distance(p1, p2):
    """Hàm phụ để tính khoảng cách Euclide giữa 2 điểm."""
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def detect_objects_pro(image_path, draw_result=True):
    """
    Hàm phát hiện vật thể phiên bản PRO: Cố gắng loại bỏ phần chiều cao/bóng đổ.
    Sử dụng phép Erode để thu nhỏ mask màu, giữ lại phần mặt trên.
    *** Nâng cấp: Trả về các ảnh mask để gỡ lỗi. ***
    """
    image = cv2.imread(image_path)
    if image is None:
        print(f"Lỗi: Không đọc được ảnh từ đường dẫn: {image_path}")
        # Trả về thêm giá trị None cho các ảnh mask mới
        return [], (0, 0), None, None, None

    output_image = image.copy()
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # Dải màu để lọc (giữ nguyên)
    masks = {
        "red": cv2.inRange(hsv, (0, 100, 100), (10, 255, 255)) | cv2.inRange(hsv, (160, 100, 100), (180, 255, 255)),
        "blue": cv2.inRange(hsv, (100, 100, 100), (130, 255, 255)),
        "yellow": cv2.inRange(hsv, (20, 100, 100), (35, 255, 255)),
        "green": cv2.inRange(hsv, (40, 50, 60), (70, 255, 255))
    }
    color_map = {
        "red": (0, 0, 255),
        "blue": (255, 0, 0),
        "yellow": (0, 255, 255),
        "green": (0, 255, 0)
    }
    objects = []

    # <<< PHẦN THÊM MỚI ĐỂ TẠO ẢNH MASK TỔNG HỢP >>>
    # Tạo ảnh đen để chứa tất cả các mask
    h, w, _ = image.shape
    initial_masks_combined = np.zeros((h, w), dtype=np.uint8)
    eroded_masks_combined = np.zeros((h, w), dtype=np.uint8)

    # Kernel erode
    erosion_kernel = np.ones((7, 7), np.uint8)

    for color, mask in masks.items():
        # Bỏ qua nếu mask không có màu nào
        if cv2.countNonZero(mask) == 0:
            continue

        # Hợp nhất mask ban đầu vào ảnh tổng hợp
        initial_masks_combined = cv2.bitwise_or(initial_masks_combined, mask)

        # Áp dụng phép co ERODE
        eroded_mask = cv2.erode(mask, erosion_kernel, iterations=1)

        # Hợp nhất mask đã erode vào ảnh tổng hợp
        eroded_masks_combined = cv2.bitwise_or(eroded_masks_combined, eroded_mask)

        # Tìm contours trên mask đã được "làm sạch"
        contours, _ = cv2.findContours(eroded_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 4000:
                continue

            M = cv2.moments(cnt)
            if M['m00'] == 0: continue
            cx, cy = int(M['m10'] / M['m00']), int(M['m01'] / M['m00'])

            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)

            if len(approx) == 4:
                pts = approx.reshape(4, 2)
                side_lengths = [calculate_distance(pts[i], pts[(i + 1) % 4]) for i in range(4)]
                if max(side_lengths) == 0: continue
                shape_ratio = min(side_lengths) / max(side_lengths)

                shape = "square" if shape_ratio >= 0.90 else "rectangle"  # Giảm ngưỡng xuống 0.90

                detail = shape
                if shape == "square":
                    if 30000 < area < 110000:
                        detail = "small square"
                    elif area >= 110000:
                        detail = "large square"
                else:
                    if 80000 < area < 200000:
                        detail = "small rectangle"
                    elif area >= 200000:
                        detail = "large rectangle"

                if draw_result:
                    cv2.drawContours(output_image, [approx], -1, color_map[color], 3)
                    label = f"{detail} (ratio: {shape_ratio:.2f})"
                    cv2.putText(output_image, label, (cx - 70, cy - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                                color_map[color], 2)

                objects.append({
                    "color": color, "pixel": (cx, cy), "area": area,
                    "shape": shape, "detail": detail, "bbox": cv2.boundingRect(cnt),
                    "aspect_ratio": shape_ratio
                })

    # Trả về các ảnh mask đã tạo
    return objects, image.shape, output_image, initial_masks_combined, eroded_masks_combined


class DobotClient:
    def __init__(self, ip="192.168.1.6"):
        try:
            self.dash = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.dash.connect((ip, 29999))
            self.motion = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.motion.connect((ip, 30003))
            print("Đã kết nối thành công với Dobot.")
        except socket.error as e:
            print(f"LỖI KẾT NỐI DOBOT: {e}")
            self.dash = None
            self.motion = None

    def send(self, sock, cmd):
        if sock is None: return "Lỗi: Chưa kết nối."
        sock.sendall((cmd + '\n').encode())
        return sock.recv(1024).decode()

    def enable_robot(self):
        return self.send(self.dash, "EnableRobot()")

    def clear_error(self):
        return self.send(self.dash, "ClearError()")

    def movej(self, x, y, z, r, speedj=None, accj=None):
        cmd = f"MovJ({x},{y},{z},{r}"
        if speedj is not None: cmd += f",SpeedJ={speedj}"
        if accj is not None: cmd += f",AccJ={accj}"
        cmd += ")"
        return self.send(self.motion, cmd)

    def movel(self, x, y, z, r, speedl=None, accl=None):
        cmd = f"MovL({x},{y},{z},{r}"
        if speedl is not None: cmd += f",SpeedL={speedl}"
        if accl is not None: cmd += f",AccL={accl}"
        cmd += ")"
        return self.send(self.motion, cmd)

    def close(self):
        if self.dash: self.dash.close()
        if self.motion: self.motion.close()
        print("Đã đóng kết nối với Dobot.")


def pixel_to_robot(pixel):
    px, py = pixel
    X = px / PIXEL_TO_MM + TRUC_X
    Y = TRUC_Y - py / PIXEL_TO_MM
    Z = -140
    R = 0
    return X, Y, Z, R


def main():
    if not os.path.exists(IMG_PATH):
        print(f"Lỗi: Không tìm thấy file ảnh tại đường dẫn: {IMG_PATH}")
        return

    # <<< THAY ĐỔI: Nhận thêm các ảnh mask trả về >>>
    objects, img_shape, image_with_boxes, initial_mask, eroded_mask = detect_objects_pro(IMG_PATH, draw_result=True)

    if not objects:
        print("Không tìm thấy vật thể nào hợp lệ!")
        # Hiển thị các mask ngay cả khi không tìm thấy vật thể để gỡ lỗi
        if initial_mask is not None: cv2.imshow("Initial Mask (No Objects Found)", initial_mask)
        if eroded_mask is not None: cv2.imshow("Eroded Mask (No Objects Found)", eroded_mask)
        if initial_mask is not None or eroded_mask is not None: cv2.waitKey(0)
        return

    # <<< THAY ĐỔI: Lưu và hiển thị các ảnh mask >>>
    if image_with_boxes is not None:
        cv2.imwrite(OUT_PATH, image_with_boxes)
        print(f"Đã lưu ảnh kết quả vào {OUT_PATH}")
        cv2.imshow("Detection Result", image_with_boxes)

        # Hiển thị các ảnh mask để gỡ lỗi
        if initial_mask is not None:
            cv2.imwrite(DEBUG_INITIAL_MASK_PATH, initial_mask)
            cv2.imshow("Initial Mask (All Colors)", initial_mask)
            print(f"Đã lưu ảnh mask ban đầu vào {DEBUG_INITIAL_MASK_PATH}")
        if eroded_mask is not None:
            cv2.imwrite(DEBUG_ERODED_MASK_PATH, eroded_mask)
            cv2.imshow("Eroded Mask (All Colors)", eroded_mask)
            print(f"Đã lưu ảnh mask sau khi erode vào {DEBUG_ERODED_MASK_PATH}")

        # Thay đổi waitKey để người dùng có thời gian xem ảnh
        print("\n>>> Hiển thị các ảnh kết quả. Nhấn phím bất kỳ trên cửa sổ ảnh để tiếp tục... <<<")
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    print("\n--- Kết quả phát hiện ---")
    for i, obj in enumerate(objects, 1):
        print(
            f"#{i}: {obj['color']} | Loại: {obj['detail']} | Diện tích: {obj['area']:.1f} | Tỷ lệ cạnh (chính xác): {obj['aspect_ratio']:.2f} | Pixel: {obj['pixel']}")
    print("------------------------\n")

    # Khởi tạo robot
    robot = DobotClient()
    if robot.dash is None:
        print("Bỏ qua phần điều khiển robot do lỗi kết nối.")
        return

    print("Enable robot:", robot.enable_robot())
    time.sleep(0.5)
    print("Clear error:", robot.clear_error())
    time.sleep(0.2)

    for i, obj in enumerate(objects, 1):
        x, y, z, r = pixel_to_robot(obj['pixel'], img_shape)
        print(f"({i}) Robot đi tới {obj['color']} ({x:.1f}, {y:.1f}, {z:.1f}, {r:.1f})")
        # --- LOGIC ĐIỀU KHIỂN ROBOT CỦA BẠN GIỮ NGUYÊN ---
        robot.movej(400, -15, 0, 0, speedj=50, accj=60)
        robot.movej(x, y, z + 50, r, speedj=25, accj=30)
        robot.send(robot.motion, "DO(5,0)")
        robot.movel(x, y, z, r, speedl=10, accl=15)
        time.sleep(1)
        robot.send(robot.motion, "DO(1,1)")
        time.sleep(1)
        robot.movel(x, y, z + 50, r, speedl=10, accl=25)
        time.sleep(0.5)

        # Phân loại điểm đặt
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
            # Xử lý các trường hợp còn lại nếu cần
            print(f"Không có vị trí đặt cho {obj['detail']} màu {obj['color']}.")

    time.sleep(0.5)
    robot.movej(400, -15, 0, 0, speedj=60, accj=60)
    robot.send(robot.motion, "DO(5,0)")
    robot.close()

    print("Đã hoàn thành nhặt tất cả vật thể.")


if __name__ == "__main__":
    main()