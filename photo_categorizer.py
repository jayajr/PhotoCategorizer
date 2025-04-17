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
                             QTableWidgetItem, QHeaderView, QInputDialog)
from PyQt5.QtGui import QPixmap, QImage, QTransform
from PyQt5.QtCore import Qt
from PIL import Image, ExifTags
import io
import datetime
import hashlib

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

class CategoryDialog(QDialog):
    def __init__(self, categories, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Categories")
        self.setMinimumSize(400, 300)
        
        layout = QVBoxLayout(self)
        
        # Create table for categories
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Category", "Key"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        
        # Fill table with categories (excluding "deleted")
        for category, key in [(c, k) for c, k in categories.items() if c != "deleted"]:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(category))
            self.table.setItem(row, 1, QTableWidgetItem(key))
        
        layout.addWidget(self.table)
        
        # Add buttons for adding/removing categories
        button_layout = QHBoxLayout()
        add_button = QPushButton("Add Category")
        add_button.clicked.connect(self.add_category)
        button_layout.addWidget(add_button)
        
        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self.remove_category)
        button_layout.addWidget(remove_button)
        
        layout.addLayout(button_layout)
        
        # Add a note about nested categories
        note_label = QLabel("Note: For nested categories, use '/' as separator (e.g., 'animals/birds')")
        layout.addWidget(note_label)
        
        # Dialog buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def add_category(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem("New Category"))
        self.table.setItem(row, 1, QTableWidgetItem("C"))
    
    def remove_category(self):
        for row in sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)
    
    def get_categories(self):
        categories = {"deleted": "Delete"}  # Always include the special deleted category
        for row in range(self.table.rowCount()):
            category_name = self.table.item(row, 0).text().strip()
            key = self.table.item(row, 1).text().strip()
            if category_name and key:
                categories[category_name] = key
        return categories

class KeybindDialog(QDialog):
    def __init__(self, keybinds, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Keybinds")
        self.setMinimumSize(400, 200)
        
        layout = QVBoxLayout(self)
        grid = QGridLayout()
        
        # Add labels and inputs for each keybind
        self.inputs = {}
        for row, (action, key) in enumerate(keybinds.items()):
            grid.addWidget(QLabel(f"{action}:"), row, 0)
            self.inputs[action] = QLineEdit(key)
            grid.addWidget(self.inputs[action], row, 1)
        
        # Add a note about the Delete key
        note_label = QLabel("Note: The Delete key is hardcoded for the 'deleted' category")
        grid.addWidget(note_label, row + 1, 0, 1, 2)
        
        layout.addLayout(grid)
        
        # Dialog buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def get_keybinds(self):
        return {action: input_field.text().strip() for action, input_field in self.inputs.items()}

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
        
        # Load config if it exists
        self.load_config()
        
        # Create output directories
        self.setup_directories()
        
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
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    saved_config = json.load(f)
                    
                # Update keybinds
                if 'keybinds' in saved_config:
                    self.keybinds.update(saved_config['keybinds'])
                
                # Update categories (preserving "deleted")
                if 'categories' in saved_config:
                    for category, key in saved_config['categories'].items():
                        if category != "deleted":
                            self.categories[category] = key
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
        
        return image_files
    
    def setup_ui(self):
        self.setWindowTitle("Photo Categorizer")
        self.setMinimumSize(900, 700)
        
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        
        # Config buttons
        config_layout = QHBoxLayout()
        edit_categories_btn = QPushButton("Edit Categories")
        edit_categories_btn.clicked.connect(self.edit_categories)
        config_layout.addWidget(edit_categories_btn)
        
        edit_keybinds_btn = QPushButton("Edit Keybinds")
        edit_keybinds_btn.clicked.connect(self.edit_keybinds)
        config_layout.addWidget(edit_keybinds_btn)
        
        # Add custom name button
        custom_name_btn = QPushButton("Custom Name")
        custom_name_btn.clicked.connect(self.prompt_custom_name)
        config_layout.addWidget(custom_name_btn)
        
        main_layout.addLayout(config_layout)
        
        # Controls label
        self.controls_label = QLabel()
        self.update_controls_label()
        self.controls_label.setAlignment(Qt.AlignLeft)
        main_layout.addWidget(self.controls_label)
        
        # Image display
        self.image_frame = QFrame()
        self.image_frame.setFrameShape(QFrame.StyledPanel)
        self.image_frame.setLineWidth(1)
        image_layout = QVBoxLayout(self.image_frame)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        image_layout.addWidget(self.image_label)
        main_layout.addWidget(self.image_frame)
        
        # Status label
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)
        
        # Custom name status
        self.custom_name_label = QLabel()
        self.custom_name_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.custom_name_label)
        self.update_custom_name_label()
        
        self.setCentralWidget(main_widget)
        self.setFocusPolicy(Qt.StrongFocus)
        
        # Display first image
        self.display_current_image()
        self.show()
    
    def update_custom_name_label(self):
        """Update the custom name label to show the current custom name status."""
        if not self.image_files or self.current_index >= len(self.image_files):
            self.custom_name_label.setText("")
            return
            
        current_file = str(self.image_files[self.current_index])
        if current_file in self.custom_names:
            self.custom_name_label.setText(f"Custom name: {self.custom_names[current_file]}")
        else:
            self.custom_name_label.setText("No custom name set (using hash)")
    
    def update_controls_label(self):
        """Update the controls label with current keybinds and categories."""
        instructions = [
            "Controls:",
            f"{self.keybinds['next']} = next image",
            f"{self.keybinds['previous']} = previous image",
            f"{self.keybinds['quit']} = quit",
            "Delete/Backspace = move to deleted folder",
            f"{self.keybinds['rotate_clockwise']} = rotate image clockwise",
            f"{self.keybinds['rotate_counterclockwise']} = rotate image anticlockwise",
            f"{self.keybinds['custom_name']} = set custom name (replaces hash)\n",
            "Categories:"
        ]
        
        # Add categories except "deleted"
        for category, key in self.categories.items():
            if category != "deleted":
                # Make nested categories more readable (e.g., "animals/birds" -> "animals > birds")
                display_category = category.replace('/', ' > ')
                instructions.append(f"{key} = move to {display_category} folder")
        
        self.controls_label.setText("\n".join(instructions))
    
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
    
    def keyPressEvent(self, event):
        key = event.text()
        
        # Handle navigation keybinds
        if key.lower() == self.keybinds['quit'].lower():
            self.close()
        elif key.lower() == self.keybinds['next'].lower() and self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self.current_rotation = 0  # Reset rotation for new image
            self.display_current_image()
        elif key.lower() == self.keybinds['previous'].lower() and self.current_index > 0:
            self.current_index -= 1
            self.current_rotation = 0  # Reset rotation for new image
            self.display_current_image()
        # Handle Delete key for "deleted" category
        elif event.key() == Qt.Key_Delete or event.key() == Qt.Key_Backspace:
            self.categorize_image("deleted")
        # Handle clockwise rotation
        elif key.lower() == self.keybinds['rotate_clockwise'].lower():
            self.rotate_image(90)
        # Handle counterclockwise rotation
        elif key.lower() == self.keybinds['rotate_counterclockwise'].lower():
            self.rotate_image(-90)
        # Handle custom name prompt (Enter key by default)
        elif (event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter) or \
             (key.lower() == self.keybinds['custom_name'].lower()):
            self.prompt_custom_name()
        # Handle category keybinds
        else:
            for category, bind in self.categories.items():
                if key.lower() == bind.lower():
                    self.categorize_image(category)
                    break
    
    def rotate_image(self, degrees):
        """Rotate the displayed image by the specified degrees."""
        self.current_rotation = (self.current_rotation + degrees) % 360
        self.display_current_image()
    
    def display_current_image(self):
        if not self.image_files:
            QMessageBox.information(self, "Complete", "No more images to categorize.")
            # Ensure we close cleanly with a slight delay to allow the message box to be dismissed
            self.close()
            return
            
        if 0 <= self.current_index < len(self.image_files):
            img_path = self.image_files[self.current_index]
            self.status_label.setText(f"Image {self.current_index + 1} of {len(self.image_files)}: {img_path.name}")
            
            # Update custom name label whenever we display a new image
            self.update_custom_name_label()
            
            try:
                # Check if it's a RAW file
                is_raw = img_path.suffix.lower() in ['.raw', '.cr2', '.nef', '.arw', '.dng', '.orf', '.rw2', '.pef', '.raf']
                
                if is_raw:
                    # Extract EXIF data for RAW files
                    with open(img_path, 'rb') as raw_file:
                        tags = exifread.process_file(raw_file)
                        # Extract preview image if available
                        try:
                            # For RAW files that PIL can't directly open, use the thumbnail from exifread
                            img = Image.open(img_path)
                            img.thumbnail((800, 600), Image.LANCZOS)
                        except Exception:
                            # If PIL fails, show a placeholder or message
                            self.image_label.setText(f"RAW file detected: {img_path.name}\nPreview not available")
                            return
                else:
                    # Regular image handling
                    img = Image.open(img_path)
                    img.thumbnail((800, 600), Image.LANCZOS)
                
                # Apply rotation if needed
                if self.current_rotation != 0:
                    img = img.rotate(-self.current_rotation, expand=True)
                
                # Convert PIL image to QPixmap for display
                img_data = img.convert("RGB").tobytes("raw", "RGB")
                qimg = QImage(img_data, img.width, img.height, img.width * 3, QImage.Format_RGB888)
                self.image_label.setPixmap(QPixmap.fromImage(qimg))
                self.adjustSize()
            except Exception as e:
                self.status_label.setText(f"Error loading image: {e}")
        else:
            self.status_label.setText("No more images to display")
    
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
                    # Look for orientation
                    for tag, tag_name in ExifTags.TAGS.items():
                        if tag_name == 'Orientation' and tag in exif_data:
                            orientation = exif_data[tag]
                        # Look for date
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
                
                # Use custom name if available, otherwise generate hash
                if current_file in self.custom_names:
                    custom_name = self.custom_names[current_file]
                    
                    # Track usage count for this name
                    if custom_name in self.name_counts:
                        self.name_counts[custom_name] += 1
                    else:
                        self.name_counts[custom_name] = 1
                    
                    # Format name according to count
                    count = self.name_counts[custom_name]
                    if count == 1:
                        name_part = custom_name
                    else:
                        name_part = f"{custom_name}-{count}"
                else:
                    # Generate a simple hash from the image content
                    img_hash = hashlib.md5(img.tobytes()).hexdigest()[:8]
                    name_part = img_hash
                
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
                        orientation_tag = None
                        for tag, tag_name in ExifTags.TAGS.items():
                            if tag_name == 'Orientation':
                                orientation_tag = tag
                                break
                        
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