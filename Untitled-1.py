from MvCameraControl_class import *
import sys, os

# Lấy đường dẫn đến thư mục hiện tại của script
HERE = os.path.dirname(os.path.abspath(__file__))

# Giả sử SDK Python của MVS nằm trong thư mục con 'MVS'
SDK_PYTHON = os.path.join(HERE, "MVS")
sys.path.insert(0, SDK_PYTHON)

# Bây giờ import sẽ tìm thấy file MvCameraControl_class.py ở đó
from MvCameraControl_class import MvCamera, MV_CC_DEVICE_INFO_LIST, MV_CC_ENUMDEV_TYPE

# … tiếp phần code khởi tạo camera …

# 1. Khởi tạo và liệt kê thiết bị
deviceList = MV_CC_DEVICE_INFO_LIST()
MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE | MV_USB_DEVICE, deviceList)

# 2. Mở camera đầu tiên
cam = MvCamera()
cam.MV_CC_CreateHandle(deviceList.pDeviceInfo[0])
cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)

# 3. Cấu hình exposure/gain nếu cần
cam.MV_CC_SetEnumValue("ExposureAuto", 0)      # Off
cam.MV_CC_SetFloatValue("ExposureTime", 20000) # µs

# 4. Bắt đầu streaming
cam.MV_CC_StartGrabbing()

# 5. Lấy frame
while True:
    st, frame_buf = cam.MV_CC_GetOneFrameTimeout(1000)
    if st == 0:
        # chuyển raw buffer sang numpy array rồi cv2.imshow
        img = frame_buf.nData  # tuỳ SDK, cần convert format
        # ...
    # break theo điều kiện

# 6. Dọn dẹp
cam.MV_CC_StopGrabbing()
cam.MV_CC_CloseDevice()
