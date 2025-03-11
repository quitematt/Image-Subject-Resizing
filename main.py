from PIL import Image
import os
import numpy as np
import logging
import tkinter as tk
from tkinter import filedialog, ttk
import threading
import queue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("image_processing.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def resize_and_center_image(image_path, output_path):
    logger.info(f"Processing image: {image_path}")
    
    try:
        # Open the image
        img = Image.open(image_path).convert("RGBA")
        logger.debug(f"Image opened and converted to RGBA")
        
        # Create a solid white background image of the same size
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        
        # Composite the image onto the white background to handle transparency
        comp = Image.alpha_composite(bg, img)
        logger.debug(f"Image composited with white background")
        
        # Convert to numpy array for more precise content detection
        img_array = np.array(comp)
        
        # Find non-white pixels
        r, g, b, _ = img_array.T
        non_white = (r < 250) | (g < 250) | (b < 250)
        non_white_positions = np.where(non_white.T)
        
        # Check if any non-white pixels were found
        if len(non_white_positions[0]) == 0:
            logger.warning(f"Skipping {image_path}: No subject detected")
            return False
        
        logger.debug(f"Non-white pixels found: {len(non_white_positions[0])}")
        
        # Find bounding box
        min_y, min_x = np.min(non_white_positions[0]), np.min(non_white_positions[1])
        max_y, max_x = np.max(non_white_positions[0]), np.max(non_white_positions[1])
        
        # Add a small margin (5 pixels) around the content
        margin = 5
        min_x = max(0, min_x - margin)
        min_y = max(0, min_y - margin)
        max_x = min(img.width - 1, max_x + margin)
        max_y = min(img.height - 1, max_y + margin)
        
        # Create the bounding box
        bbox = (min_x, min_y, max_x + 1, max_y + 1)
        
        # Log detailed information
        logger.info(f"Image: {os.path.basename(image_path)}")
        logger.info(f"Original size: {img.size}")
        logger.info(f"Detected bbox: {bbox}")
        logger.info(f"Content dimensions: {bbox[2]-bbox[0]}x{bbox[3]-bbox[1]} pixels")
        logger.info(f"Non-white pixels found: {len(non_white_positions[0])}")
        
        # Crop to content
        img_cropped = img.crop(bbox)
        logger.debug(f"Image cropped to bounding box")
        
        # Determine resizing dimensions
        w, h = img_cropped.size
        if w > h:
            new_w = 485
            new_h = int((h / w) * 485)
        else:
            new_h = 485
            new_w = int((w / h) * 485)

        flagged_path = None

        if min(w, h) < 485:
            flagged_path = (
                output_path.replace(".", "_CHECK_PIXELATION.") if "." in output_path 
                else output_path + "_CHECK_PIXELATION"
            )
            logger.warning(f"Image dimensions too small (w: {w}, h: {h}). May pixelate: {flagged_path}")

        # Resize image
        img_resized = img_cropped.resize((new_w, new_h), Image.LANCZOS)
        logger.debug(f"Image resized to {new_w}x{new_h}")

        # Create a 500x500 canvas and paste the resized image in the center
        canvas = Image.new("RGB", (500, 500), (255, 255, 255))
        paste_x = (500 - new_w) // 2
        paste_y = (500 - new_h) // 2
        canvas.paste(img_resized, (paste_x, paste_y), img_resized)
        logger.debug("Image centered on 500x500 canvas")

        # Save output
        save_path = flagged_path if flagged_path else output_path
        canvas.save(save_path, "PNG")
        logger.info(f"Saved to: {save_path}")
        logger.info("-" * 40)
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing {image_path}: {str(e)}", exc_info=True)
        return False

def process_directory(input_folder, output_folder, progress_queue=None):
    logger.info(f"Starting batch processing of images from {input_folder} to {output_folder}")
    
    # Create output directory if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    
    # Count total files to process
    image_files = [f for f in os.listdir(input_folder) 
                  if f.lower().endswith(("png", "jpg", "jpeg", "webp", "gif"))]
    
    total_files = len(image_files)
    logger.info(f"Found {total_files} image files to process")
    
    if progress_queue:
        progress_queue.put(('max', total_files))
        progress_queue.put(('status', f"Found {total_files} images to process"))
    
    # Process each file
    processed_count = 0
    success_count = 0
    
    for i, filename in enumerate(image_files):
        input_path = os.path.join(input_folder, filename)
        output_path = os.path.join(output_folder, os.path.splitext(filename)[0] + ".png")
        
        logger.info(f"Processing file {i+1} of {total_files}: {filename}")
        
        if progress_queue:
            progress_queue.put(('status', f"Processing {i+1}/{total_files}: {filename}"))
        
        result = resize_and_center_image(input_path, output_path)
        processed_count += 1
        
        if result:
            success_count += 1
            
        if progress_queue:
            progress_queue.put(('progress', processed_count))
    
    logger.info(f"Batch processing complete. Successfully processed {success_count} of {total_files} images.")
    
    if progress_queue:
        progress_queue.put(('status', f"Complete! Successfully processed {success_count} of {total_files} images."))
        progress_queue.put(('done', None))

def browse_folder():
    folder = filedialog.askdirectory(title="Select Input Folder")
    if folder:
        folder_var.set(folder)
        status_var.set(f"Selected folder: {folder}")

def start_processing():
    input_folder = folder_var.get()
    
    if not input_folder or not os.path.isdir(input_folder):
        status_var.set("Please select a valid input folder")
        return
    
    # Create output folder name based on input folder
    input_folder_name = os.path.basename(input_folder)
    parent_dir = os.path.dirname(input_folder)
    output_folder = os.path.join(parent_dir, f"{input_folder_name}_resized")
    
    # Disable button during processing
    process_button.configure(state="disabled")
    progress_var.set(0)
    status_var.set("Starting processing...")
    
    # Start processing in a separate thread
    processing_thread = threading.Thread(
        target=process_directory,
        args=(input_folder, output_folder, progress_queue)
    )
    processing_thread.daemon = True
    processing_thread.start()

def check_queue():
    try:
        while True:
            message_type, message_value = progress_queue.get_nowait()
            
            if message_type == 'status':
                status_var.set(message_value)
            elif message_type == 'progress':
                progress_var.set(message_value)
            elif message_type == 'max':
                progress_bar.configure(maximum=message_value)
            elif message_type == 'done':
                process_button.configure(state="normal")
            
            progress_queue.task_done()
    
    except queue.Empty:
        pass
    
    root.after(100, check_queue)

if __name__ == "__main__":
    # Create the main window
    root = tk.Tk()
    root.title("Image Resizer")
    root.geometry("500x300")
    root.resizable(False, False)
    
    # Set up the queue for thread communication
    progress_queue = queue.Queue()
    
    # Main frame
    main_frame = ttk.Frame(root, padding="20")
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    # Title
    title_label = ttk.Label(main_frame, text="Image Resizer", font=("Helvetica", 16))
    title_label.pack(pady=(0, 20))
    
    # Input folder selection
    folder_frame = ttk.Frame(main_frame)
    folder_frame.pack(fill=tk.X, pady=5)
    
    folder_label = ttk.Label(folder_frame, text="Input Folder:")
    folder_label.pack(side=tk.LEFT, padx=(0, 10))
    
    folder_var = tk.StringVar()
    folder_entry = ttk.Entry(folder_frame, textvariable=folder_var, width=30)
    folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
    
    browse_button = ttk.Button(folder_frame, text="Browse", command=browse_folder)
    browse_button.pack(side=tk.RIGHT)
    
    # Progress bar
    progress_frame = ttk.Frame(main_frame)
    progress_frame.pack(fill=tk.X, pady=20)
    
    progress_var = tk.DoubleVar()
    progress_bar = ttk.Progressbar(progress_frame, variable=progress_var, maximum=100)
    progress_bar.pack(fill=tk.X)
    
    # Status label
    status_var = tk.StringVar()
    status_var.set("Select an input folder to begin")
    status_label = ttk.Label(main_frame, textvariable=status_var, wraplength=460)
    status_label.pack(fill=tk.X, pady=10)
    
    # Process button
    process_button = ttk.Button(main_frame, text="Resize Images", command=start_processing)
    process_button.pack(pady=10)
    
    # Start queue checker
    root.after(100, check_queue)
    
    # Start the main loop
    root.mainloop()