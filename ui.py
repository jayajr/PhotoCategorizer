from PyQt5.QtWidgets import (QLabel, QVBoxLayout, QWidget, 
                             QDialog, QLineEdit, QHBoxLayout, QDialogButtonBox, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QInputDialog, QSizePolicy, QPushButton,
                             QFrame, QGridLayout, QScrollArea)
from PyQt5.QtGui import QPixmap, QImage, QTransform
from PyQt5.QtCore import Qt, QSize

class CategoryDialog(QDialog):
    def __init__(self, categories, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Categories")
        self.setMinimumSize(400, 300)
        
        layout = QVBoxLayout(self)
        
        # Create and configure table
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Category", "Key"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        
        # Fill table with non-deleted categories
        for category, key in [(c, k) for c, k in categories.items() if c != "deleted"]:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(category))
            self.table.setItem(row, 1, QTableWidgetItem(key))
        
        layout.addWidget(self.table)
        
        # Add action buttons
        button_layout = QHBoxLayout()
        button_configs = [
            ("Add Category", self.add_category),
            ("Remove Selected", self.remove_category)
        ]
        
        for text, callback in button_configs:
            btn = QPushButton(text)
            btn.clicked.connect(callback)
            button_layout.addWidget(btn)
            
        layout.addLayout(button_layout)
        
        # Add notes
        for note in [
            "Note: For nested categories, use '/' as separator (e.g., 'animals/birds')",
            "Note: Keys are case sensitive (e.g., 'N' is different from 'n')"
        ]:
            layout.addWidget(QLabel(note))
        
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
        categories.update({
            self.table.item(row, 0).text().strip(): self.table.item(row, 1).text().strip()
            for row in range(self.table.rowCount())
            if self.table.item(row, 0).text().strip() and self.table.item(row, 1).text().strip()
        })
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
        
        # Add notes
        for i, note in enumerate([
            "Note: The Delete key is hardcoded for the 'deleted' category",
            "Note: Keybinds are case sensitive (e.g., 'N' is different from 'n')"
        ]):
            grid.addWidget(QLabel(note), row + i + 1, 0, 1, 2)
        
        layout.addLayout(grid)
        
        # Dialog buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def get_keybinds(self):
        return {action: input_field.text().strip() for action, input_field in self.inputs.items()}

class PhotoCategorizerUI:
    def setup_ui(self, main_window, keybinds, categories):
        """Set up the main UI for the photo categorizer"""
        main_window.setWindowTitle("Photo Categorizer")
        main_window.setMinimumSize(900, 700)
        
        # Create main widget and layout
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        
        # Add config buttons
        config_layout = QHBoxLayout()
        
        # Create standard buttons
        for text, callback in [
            ("Edit Categories", main_window.edit_categories),
            ("Edit Keybinds", main_window.edit_keybinds),
            ("Custom Name", main_window.prompt_custom_name)
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(callback)
            config_layout.addWidget(btn)
        
        # Add toggle help button (needs instance attribute)
        main_window.toggle_help_btn = QPushButton("Hide Help")
        main_window.toggle_help_btn.clicked.connect(main_window.toggle_help)
        config_layout.addWidget(main_window.toggle_help_btn)
        
        main_layout.addLayout(config_layout)
        
        # Controls label
        main_window.controls_label = QLabel()
        main_window.controls_label.setAlignment(Qt.AlignLeft)
        main_window.controls_label.setTextFormat(Qt.RichText)
        main_window.controls_label.setMargin(5)
        main_window.controls_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.update_controls_label(main_window, keybinds, categories)
        main_layout.addWidget(main_window.controls_label)
        
        # Keep reference for compatibility
        main_window.controls_scroll_area = main_window.controls_label
        
        # Image display
        main_window.image_frame = QFrame()
        main_window.image_frame.setFrameShape(QFrame.StyledPanel)
        main_window.image_frame.setLineWidth(1)
        
        main_window.image_label = QLabel()
        main_window.image_label.setAlignment(Qt.AlignCenter)
        main_window.image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        main_window.image_label.setScaledContents(False)
        
        image_layout = QVBoxLayout(main_window.image_frame)
        image_layout.addWidget(main_window.image_label)
        main_layout.addWidget(main_window.image_frame, 1)
        
        # Status footer
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(5)
        
        # Create status labels
        for attr_name, alignment in [
            ("status_label", Qt.AlignLeft),
            ("custom_name_label", Qt.AlignRight)
        ]:
            label = QLabel()
            label.setAlignment(alignment)
            label.setMaximumHeight(20)
            setattr(main_window, attr_name, label)
            footer_layout.addWidget(label)
        
        main_layout.addLayout(footer_layout)
        
        # Set central widget and focus policy
        main_window.setCentralWidget(central_widget)
        main_window.setFocusPolicy(Qt.StrongFocus)

    def update_controls_label(self, main_window, keybinds, categories):
        """Update the controls label with current keybinds and categories."""
        # Generate control instructions
        controls = [
            "Controls:",
            f"{keybinds['next']} = next image",
            f"{keybinds['previous']} = previous image",
            f"{keybinds['quit']} = quit",
            "Delete/Backspace = move to deleted folder",
            f"{keybinds['rotate_clockwise']} = rotate image clockwise",
            f"{keybinds['rotate_counterclockwise']} = rotate image anticlockwise",
            f"{keybinds['custom_name']} = set custom name (replaces hash)",
            "",
            "<b>Note: Keys are case sensitive</b>"
        ]
        
        # Generate category instructions
        category_instructions = ["Categories:"]
        category_instructions.extend([
            f"{key} = move to {category.replace('/', ' > ')} folder"
            for category, key in categories.items()
            if category != "deleted"
        ])
        
        # Set HTML text
        main_window.controls_label.setText("".join([
            "<table><tr>",
            "<td style='vertical-align:top; padding-right:20px'>",
            "<br>".join(controls),
            "</td><td style='vertical-align:top'>",
            "<br>".join(category_instructions),
            "</td></tr></table>"
        ]))
        
    def update_custom_name_label(self, main_window, custom_names, sequence_counter, image_files, current_index):
        """Update the custom name label to show the current custom name status."""
        if not image_files or current_index >= len(image_files):
            main_window.custom_name_label.setText("")
            return
            
        current_file = str(image_files[current_index])
        main_window.custom_name_label.setText(
            f"Custom name: {custom_names[current_file]}" if current_file in custom_names
            else f"No custom name set (using sequence: {sequence_counter:08d})"
        ) 
