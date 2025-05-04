#!/usr/bin/env python3

import os
import sys
import json
from pathlib import Path
import shutil
import exifread
from PyQt5.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, 
                             QFrame, QMessageBox, QPushButton, QHBoxLayout, QGridLayout,
                             QDialog, QLineEdit, QDialogButtonBox, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QInputDialog, QScrollArea,
                             QSizePolicy)
from PyQt5.QtGui import QPixmap, QImage, QTransform
from PyQt5.QtCore import Qt, QSize
from PIL import Image, ExifTags
import io
import datetime
import hashlib
import re
from ui import CategoryDialog, KeybindDialog, PhotoCategorizerUI

# Try to import piexif for better EXIF handling
try:
    import piexif
    HAS_PIEXIF = True
except ImportError:
    HAS_PIEXIF = False

# Default keybinds
DEFAULT_KEYBINDS = {
    "next": "N",
    "previous": "P",
    "quit": "Q",
    "rotate_clockwise": "R",
    "rotate_counterclockwise": "E",
    "custom_name": "Return"  # New keybind for custom naming
}

# Default categories (with "deleted" being handled specially)
DEFAULT_CATEGORIES = {
    "deleted": "Delete"  # Special category
}

class PhotoCategorizer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.in_dir = Path("in")
        self.out_dir = Path("out")
        self.originals_dir = Path("out/originals")
        self.config_file = Path("config.json")
        
        # Initialize keybinds and categories from defaults
        self.keybinds = DEFAULT_KEYBINDS.copy()
        self.categories = DEFAULT_CATEGORIES.copy()
        
        # Dictionary to store custom names for specific files
        self.custom_names = {}
        
        # Dictionary to track how many times each custom name has been used
        self.name_counts = {}
        
        # Counter for sequential naming - will be initialized after directories are created
        self.sequence_counter = 1
        
        # Help visibility state
        self.help_visible = True
        
        # Cache for current image pixmap
        self.current_pixmap = None
        
        # UI component
        self.ui = PhotoCategorizerUI()
        
        # Load config if it exists
        self.load_config()
        
        # Create output directories
        self.setup_directories()
        
        # Initialize sequence counter based on existing files
        self.initialize_sequence_counter()
        
        # Get list of image files
        self.image_files = self.get_image_files()
        if not self.image_files:
            print("No image files found in the 'in' directory.")
            sys.exit(0)
            
        self.current_index = 0
        
        # Track rotation for the current image
        self.current_rotation = 0
        
        # Setup UI
        self.setup_ui()
    
    def closeEvent(self, event):
        """Handle application close event to ensure clean exit."""
        # Save any pending configurations
        self.save_config()
        # Accept the close event
        event.accept()
    
    def load_config(self):
        """Load configuration from JSON file if it exists."""
        if not self.config_file.exists():
            return
            
        try:
            with open(self.config_file, 'r') as f:
                saved_config = json.load(f)
                
            # Update keybinds
            if 'keybinds' in saved_config:
                self.keybinds.update(saved_config['keybinds'])
            
            # Update categories (preserving "deleted")
            if 'categories' in saved_config:
                self.categories.update({category: key for category, key in saved_config['categories'].items() if category != "deleted"})
        except Exception as e:
            print(f"Error loading config: {e}")
    
    def save_config(self):
        """Save current configuration to JSON file."""
        config = {
            'keybinds': self.keybinds,
            'categories': {k: v for k, v in self.categories.items() if k != "deleted"}
        }
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def setup_directories(self):
        """Create input and output directories."""
        self.in_dir.mkdir(exist_ok=True)
        self.out_dir.mkdir(exist_ok=True)
        self.originals_dir.mkdir(exist_ok=True)
        
        # Create category directories
        for category in self.categories:
            # Handle nested directories by creating parent directories as needed
            category_path = self.out_dir / category
            category_path.mkdir(exist_ok=True, parents=True)
    
    def initialize_sequence_counter(self):
        """Initialize the sequence counter based on existing files in the output directory."""
        # Pattern to match sequence numbers in filenames (8 digits)
        sequence_pattern = re.compile(r'-(\d{8})-')
        
        # Find all sequence numbers across all dirs except originals
        sequence_numbers = []
        for root, _, files in os.walk(self.out_dir):
            if Path(root) == self.originals_dir:
                continue
                
            for file in files:
                match = sequence_pattern.search(file)
                if match:
                    try:
                        sequence_numbers.append(int(match.group(1)))
                    except ValueError:
                        pass
        
        # Set counter to max + 1 or 1 if no sequence found
        self.sequence_counter = max(sequence_numbers, default=0) + 1
        print(f"Initialized sequence counter to {self.sequence_counter}")
    
    def get_image_files(self):
        """Get list of image files from the input directory."""
        standard_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp']
        raw_extensions = ['.raw', '.cr2', '.nef', '.arw', '.dng', '.orf', '.rw2', '.pef', '.raf']
        
        image_files = []
        
        for f in self.in_dir.iterdir():
            if not f.is_file():
                continue
                
            ext = f.suffix.lower()
            
            # Try to open with PIL first to validate standard formats
            try:
                if ext in standard_extensions:
                    # Validate with PIL
                    Image.open(f).verify()
                    image_files.append(f)
                # For raw formats, verify they can be read with exifread
                elif ext in raw_extensions:
                    with open(f, 'rb') as raw_file:
                        tags = exifread.process_file(raw_file, details=False)
                        # If we can get some basic EXIF tags, it's likely a valid RAW file
                        if tags and len(tags) > 0:
                            image_files.append(f)
            except Exception as e:
                print(f"Error validating image file {f}: {e}")
        
        # Sort image files in ascending order by name
        return sorted(image_files)
    
    def setup_ui(self):
        # Use the extracted UI component to setup
        self.ui.setup_ui(self, self.keybinds, self.categories)
        self.update_custom_name_label()
        # Display first image
        self.display_current_image()
        self.show()
    
    def update_custom_name_label(self):
        """Update the custom name label to show the current custom name status."""
        self.ui.update_custom_name_label(self, self.custom_names, self.sequence_counter, 
                                          self.image_files, self.current_index)
    
    def update_controls_label(self):
        """Update the controls label with current keybinds and categories."""
        self.ui.update_controls_label(self, self.keybinds, self.categories)
    
    def prompt_custom_name(self):
        """Prompt the user for a custom name to replace the hash for the current file."""
        if not self.image_files or self.current_index >= len(self.image_files):
            return
            
        current_file = str(self.image_files[self.current_index])
        current_custom_name = self.custom_names.get(current_file, "")
        
        text, ok = QInputDialog.getText(
            self, 'Custom Name', 
            'Enter a custom name to replace the hash:',
            text=current_custom_name
        )
        
        if ok:
            if text.strip():
                self.custom_names[current_file] = text.strip()
            elif current_file in self.custom_names:
                del self.custom_names[current_file]
                
            self.update_custom_name_label()
    
    def edit_categories(self):
        """Open dialog to edit categories."""
        dialog = CategoryDialog(self.categories, self)
        if dialog.exec_():
            self.categories = dialog.get_categories()
            self.setup_directories()
            self.update_controls_label()
            self.save_config()
    
    def edit_keybinds(self):
        """Open dialog to edit keybinds."""
        dialog = KeybindDialog(self.keybinds, self)
        if dialog.exec_():
            self.keybinds = dialog.get_keybinds()
            self.update_controls_label()
            self.save_config()
    
    def toggle_help(self):
        """Toggle the visibility of the help text."""
        self.help_visible = not self.help_visible
        self.controls_label.setVisible(self.help_visible)
        
        # Update button text
        self.toggle_help_btn.setText("Hide Help" if self.help_visible else "Show Help")
    
    def keyPressEvent(self, event):
        key = event.text()
        
        # Handle navigation keybinds
        if key == self.keybinds['quit']:
            self.close()
        elif key == self.keybinds['next'] and self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self.current_rotation = 0  # Reset rotation for new image
            self.current_pixmap = None  # Clear pixmap to force reload
            self.display_current_image()
        elif key == self.keybinds['previous'] and self.current_index > 0:
            self.current_index -= 1
            self.current_rotation = 0  # Reset rotation for new image
            self.current_pixmap = None  # Clear pixmap to force reload
            self.display_current_image()
        # Handle Delete key for "deleted" category
        elif event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.categorize_image("deleted")
        # Handle clockwise rotation
        elif key == self.keybinds['rotate_clockwise']:
            self.rotate_image(90)
        # Handle counterclockwise rotation
        elif key == self.keybinds['rotate_counterclockwise']:
            self.rotate_image(-90)
        # Handle custom name prompt (Enter key by default)
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter) or key == self.keybinds['custom_name']:
            self.prompt_custom_name()
        # Handle category keybinds
        else:
            for category, bind in self.categories.items():
                if key == bind:
                    self.categorize_image(category)
                    break
    
    def rotate_image(self, degrees):
        """Rotate the displayed image by the specified degrees."""
        self.current_rotation = (self.current_rotation + degrees) % 360
        # Clear the cached pixmap to force a reload with rotation
        self.current_pixmap = None
        self.display_current_image()
    
    def display_current_image(self):
        if not self.image_files:
            QMessageBox.information(self, "Complete", "No more images to categorize.")
            # Ensure we close cleanly with a slight delay to allow the message box to be dismissed
            self.close()
            return
            
        if not (0 <= self.current_index < len(self.image_files)):
            self.status_label.setText("No more images to display")
            return
            
        img_path = self.image_files[self.current_index]
        self.status_label.setText(f"Image {self.current_index + 1} of {len(self.image_files)}: {img_path.name}")
        
        # Update custom name label whenever we display a new image
        self.update_custom_name_label()
        
        # Always force reload of image when navigating
        self.current_pixmap = None
        
        try:
            # Check if it's a RAW file
            is_raw = img_path.suffix.lower() in ['.raw', '.cr2', '.nef', '.arw', '.dng', '.orf', '.rw2', '.pef', '.raf']
            
            if is_raw:
                # Extract EXIF data for RAW files
                with open(img_path, 'rb') as raw_file:
                    exifread.process_file(raw_file)
                    try:
                        # For RAW files that PIL can't directly open, use the thumbnail from exifread
                        img = Image.open(img_path)
                    except Exception:
                        # If PIL fails, show a placeholder or message
                        self.image_label.setText(f"RAW file detected: {img_path.name}\nPreview not available")
                        return
            else:
                # Regular image handling
                img = Image.open(img_path)
            
            # Apply rotation if needed
            if self.current_rotation != 0:
                img = img.rotate(-self.current_rotation, expand=True)
            
            # Convert PIL image to QPixmap for display
            img_data = img.convert("RGB").tobytes("raw", "RGB")
            qimg = QImage(img_data, img.width, img.height, img.width * 3, QImage.Format_RGB888)
            self.current_pixmap = QPixmap.fromImage(qimg)
            
        except Exception as e:
            self.status_label.setText(f"Error loading image: {e}")
            return
        
        # Get the size of the image frame
        frame_size = self.image_frame.size()
        # Scale the pixmap to fit the frame while maintaining aspect ratio
        scaled_pixmap = self.current_pixmap.scaled(
            frame_size, 
            Qt.KeepAspectRatio, 
            Qt.SmoothTransformation
        )
        
        self.image_label.setPixmap(scaled_pixmap)
    
    def categorize_image(self, category):
        """Move the current image to the specified category folder, 
        converting to JPEG with stripped metadata but preserving rotation."""
        if not self.image_files or self.current_index >= len(self.image_files):
            return
            
        src_path = self.image_files[self.current_index]
        current_file = str(src_path)
        
        try:
            # Check if it's a RAW file
            is_raw = src_path.suffix.lower() in ['.raw', '.cr2', '.nef', '.arw', '.dng', '.orf', '.rw2', '.pef', '.raf']
            
            # Open the image and convert to JPEG with stripped metadata
            try:
                img = Image.open(src_path)
                
                # Apply rotation if needed
                if self.current_rotation != 0:
                    img = img.rotate(-self.current_rotation, expand=True)
                
                # Convert to RGB if necessary (for PNG with transparency, etc.)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Extract metadata before stripping
                exif_data = None
                date_taken = None
                orientation = None
                
                # Try to get EXIF data
                if hasattr(img, '_getexif') and img._getexif():
                    exif_data = img._getexif()
                    # Look for orientation and date
                    for tag, tag_name in ExifTags.TAGS.items():
                        if tag_name == 'Orientation' and tag in exif_data:
                            orientation = exif_data[tag]
                        if tag_name == 'DateTimeOriginal' and tag in exif_data:
                            date_str = exif_data[tag]
                            try:
                                date_taken = datetime.datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                            except ValueError:
                                pass
                
                # If EXIF data didn't work, try exifread for RAW files
                if date_taken is None and is_raw:
                    with open(src_path, 'rb') as raw_file:
                        tags = exifread.process_file(raw_file)
                        if 'EXIF DateTimeOriginal' in tags:
                            date_str = str(tags['EXIF DateTimeOriginal'])
                            try:
                                date_taken = datetime.datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                            except ValueError:
                                pass
                
                # Fallback to file modification time if no EXIF date
                if date_taken is None:
                    date_taken = datetime.datetime.fromtimestamp(os.path.getmtime(src_path))
                
                # Determine if image is horizontal or vertical
                width, height = img.size
                orientation_char = 'h' if width >= height else 'v'
                
                # Format the new filename
                date_part = date_taken.strftime("%y%m%d")
                
                # Use custom name if available, otherwise use sequence number
                if current_file in self.custom_names:
                    custom_name = self.custom_names[current_file]
                    
                    # Track usage count for this name
                    self.name_counts[custom_name] = self.name_counts.get(custom_name, 0) + 1
                    
                    # Format name according to count
                    count = self.name_counts[custom_name]
                    name_part = custom_name if count == 1 else f"{custom_name}-{count}"
                else:
                    # Use sequence number instead of hash
                    name_part = f"{self.sequence_counter:08d}"
                    self.sequence_counter += 1
                
                new_filename = f"{date_part}-{name_part}-{orientation_char}.jpg"
                
                # Set destination path with new filename
                # Ensure the category directory exists (for nested categories)
                dst_dir = self.out_dir / category
                dst_dir.mkdir(exist_ok=True, parents=True)
                dst_path = dst_dir / new_filename
                
                # Create a new image to strip all metadata
                output = io.BytesIO()
                # Save without any EXIF
                img.save(output, format='JPEG', quality=95)
                # Create new image from bytes, which will have no metadata
                stripped_img = Image.open(output)
                
                # If original had orientation data, preserve only that
                if orientation is not None and HAS_PIEXIF:
                    try:
                        # Create minimal EXIF data with just orientation
                        exif_dict = {"0th": {}, "Exif": {}, "1st": {}, "GPS": {}}
                        # Find the orientation tag number
                        orientation_tag = next((tag for tag, tag_name in ExifTags.TAGS.items() 
                                                if tag_name == 'Orientation'), None)
                        
                        if orientation_tag:
                            exif_dict["0th"][orientation_tag] = orientation
                            
                        # Save with just orientation EXIF data
                        exif_bytes = piexif.dump(exif_dict)
                        stripped_img.save(dst_path, 'JPEG', quality=95, exif=exif_bytes)
                    except Exception as e:
                        # If there's an error with EXIF, save without it
                        QMessageBox.warning(self, "EXIF Warning", 
                                           f"Error preserving orientation: {e}")
                        stripped_img.save(dst_path, 'JPEG', quality=95)
                else:
                    # Save without any EXIF data
                    stripped_img.save(dst_path, 'JPEG', quality=95)
                    if orientation is not None and not HAS_PIEXIF:
                        QMessageBox.warning(self, "EXIF Warning", 
                                          "piexif module not found. Orientation metadata will not be preserved.")
                
                # For RAW files, keep the original if not deleted
                if is_raw and category != "deleted":
                    original_dst = (self.originals_dir / src_path.name)
                    shutil.copy(src_path, original_dst)
                
                # Remove the original file
                os.remove(src_path)
                
                # For RAW files, also handle sidecar files (.XMP, etc.)
                if is_raw:
                    for ext in ['.xmp', '.thm']:
                        sidecar = src_path.with_suffix(ext)
                        if sidecar.exists():
                            if category != "deleted":
                                # Copy sidecar files to the originals directory
                                sidecar_dst = (self.originals_dir / sidecar.name)
                                shutil.copy(sidecar, sidecar_dst)
                            # Remove the original sidecar
                            os.remove(sidecar)
                
                # Remove the file from custom_names if it was there
                if current_file in self.custom_names:
                    del self.custom_names[current_file]
                
            except Exception as e:
                # If conversion fails, just move the original file
                QMessageBox.warning(self, "Conversion Warning", 
                                   f"Could not convert to JPEG: {e}\nMoving original file.")
                
                # Ensure destination directory exists
                dst_dir = self.out_dir / category
                dst_dir.mkdir(exist_ok=True, parents=True)
                
                if is_raw and category != "deleted":
                    # Copy to originals directory
                    original_dst = (self.originals_dir / src_path.name)
                    shutil.copy(src_path, original_dst)
                    # Also move to the category directory
                    dst_file_path = dst_dir / src_path.name
                    shutil.move(src_path, dst_file_path)
                else:
                    # Just move to the category directory
                    dst_file_path = dst_dir / src_path.name
                    shutil.move(src_path, dst_file_path)
                
                # For RAW files, also move sidecar files
                if is_raw:
                    for ext in ['.xmp', '.thm']:
                        sidecar = src_path.with_suffix(ext)
                        if sidecar.exists():
                            if category != "deleted":
                                # Copy to originals directory
                                sidecar_dst = (self.originals_dir / sidecar.name)
                                shutil.copy(sidecar, sidecar_dst)
                                # Also move to category directory
                                dst_sidecar_path = dst_dir / sidecar.name
                                shutil.move(sidecar, dst_sidecar_path)
                            else:
                                # Just remove the sidecar
                                os.remove(sidecar)
            
            # Remove the processed file from the list
            self.image_files.pop(self.current_index)
            
            # Reset rotation for next image
            self.current_rotation = 0
            
            # Clear the cached pixmap for the next image
            self.current_pixmap = None
            
            # Handle end of processing or continue to next image
            if not self.image_files:
                QMessageBox.information(self, "Complete", "All images have been processed!")
                # Ensure we close cleanly
                self.close()
            elif self.current_index >= len(self.image_files):
                self.current_index = len(self.image_files) - 1
            
            self.display_current_image()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to categorize image: {e}")

    def resizeEvent(self, event):
        """Handle window resize events - update the image display to fill the new size."""
        super().resizeEvent(event)
        # Redisplay the current image to ensure it scales properly
        if hasattr(self, 'image_label') and self.image_label.pixmap() is not None:
            self.display_current_image()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PhotoCategorizer()
    # Ensure we have a proper exit code
    try:
        exit_code = app.exec_()
    except Exception as e:
        print(f"Error during application execution: {e}")
        exit_code = 1
    sys.exit(exit_code) 
