from fastapi import FastAPI, UploadFile, File
from fastapi.responses import PlainTextResponse
import subprocess
from paddleocr import PaddleOCR
from PIL import Image
import numpy as np
import os
from difflib import SequenceMatcher
from pathlib import Path
import shutil
import uvicorn
import logging

#创建FastAPI应用实例
app = FastAPI()

# 从视频文件提取字幕
def extract_subtitles(video_path: str) -> str:
    try:
        ocr = PaddleOCR(use_angle_cls=True, lang="ch")  # 加载模型
        video_name = Path(video_path).stem
        frame_output_folder = Path('./video_frames') / video_name
        frame_output_folder.mkdir(parents=True, exist_ok=True)  

        # 使用ffmpeg从视频中提取帧
        if not list(frame_output_folder.glob('*.png')):
            ffmpeg_command = ['ffmpeg', '-i', video_path, '-vf', 'fps=1', str(frame_output_folder / 'frame_%04d.png')]
            subprocess.run(ffmpeg_command, check=True)

        subtitle_height_ratio = 0.2  
        recognized_subtitles = []
        full_subtitle_text = ""
        
        #对每一帧进行OCR识别
        for img_file in sorted(os.listdir(frame_output_folder)):
            img_path = os.path.join(frame_output_folder, img_file)
            if img_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
                image = Image.open(img_path)
                #通过两点（左上角、右下角）确定矩形字幕区域，把画幅放在坐标系上的第四象限。
                width, height = image.size
                #规定了字幕区域在整个图像底部的20%部分，因此左上角的x坐标为0，y坐标为0.8倍的图像高，右下角的x坐标为图像的宽，y坐标为图像的高
                subtitle_area = (0, int(height * (1 - subtitle_height_ratio)), width, height)
                cropped_image = image.crop(subtitle_area)
                #将裁剪后的图像转换为Numpy数组。如果图像有四个通道（例如包含透明度通道），则只保留前三个通道（RGB）
                cropped_image_np = np.array(cropped_image)
                if cropped_image_np.shape[2] == 4:
                    cropped_image_np = cropped_image_np[:, :, :3]

                result = ocr.ocr(cropped_image_np, cls=True)
                if result:
                    current_subtitle = " ".join([line[1][0] for res in result for line in res if len(line) > 1 and len(line[1]) > 0])
                    current_subtitle_cleaned = ' '.join(current_subtitle.split())
                    #使用SequenceMatcher进行去重，确保相似度高于0.8的字幕不会重复添加
                    if not any(SequenceMatcher(None, current_subtitle_cleaned, old_subtitle).ratio() > 0.8 for old_subtitle in recognized_subtitles):
                        recognized_subtitles.append(current_subtitle_cleaned)
                        full_subtitle_text += current_subtitle_cleaned + " "

        return full_subtitle_text
    except Exception as e:
        logging.exception("Error processing video: %s", e)
        return "Error processing video"

#定义上传文件处理的API端点
@app.post("/extract-subtitles/")
async def extract_subtitles_endpoint(file: UploadFile = File(...)):
    with open(file.filename, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    subtitles = extract_subtitles(file.filename)
    #没必要缓存需提取字幕的视频，因此提取完成后直接删掉
    os.remove(file.filename)
    return PlainTextResponse(subtitles)

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8089, reload=True)
