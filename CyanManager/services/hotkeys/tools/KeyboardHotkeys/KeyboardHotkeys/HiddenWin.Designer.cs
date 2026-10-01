namespace KeyboardHotkeys
{
    partial class HiddenWin
    {
        /// <summary>
        ///  Required designer variable.
        /// </summary>
        private System.ComponentModel.IContainer components = null;

        /// <summary>
        ///  Clean up any resources being used.
        /// </summary>
        /// <param name="disposing">true if managed resources should be disposed; otherwise, false.</param>
        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        #region Windows Form Designer generated code

        /// <summary>
        ///  Required method for Designer support - do not modify
        ///  the contents of this method with the code editor.
        /// </summary>
        private void InitializeComponent()
        {
            keyRevealer = new TextBox();
            keyLabel = new Label();
            keyID = new TextBox();
            key_id_lbl = new Label();
            modifiers_lbl = new Label();
            modifierID = new TextBox();
            copy_btn = new Button();
            combination_view = new ListView();
            SuspendLayout();
            // 
            // keyRevealer
            // 
            keyRevealer.Location = new Point(164, 19);
            keyRevealer.Name = "keyRevealer";
            keyRevealer.Size = new Size(182, 23);
            keyRevealer.TabIndex = 0;
            // 
            // keyLabel
            // 
            keyLabel.AutoSize = true;
            keyLabel.Location = new Point(25, 22);
            keyLabel.Name = "keyLabel";
            keyLabel.Size = new Size(133, 15);
            keyLabel.TabIndex = 1;
            keyLabel.Text = "Type a key combination";
            // 
            // keyID
            // 
            keyID.Location = new Point(401, 19);
            keyID.Name = "keyID";
            keyID.Size = new Size(73, 23);
            keyID.TabIndex = 2;
            // 
            // key_id_lbl
            // 
            key_id_lbl.AutoSize = true;
            key_id_lbl.Location = new Point(352, 22);
            key_id_lbl.Name = "key_id_lbl";
            key_id_lbl.Size = new Size(43, 15);
            key_id_lbl.TabIndex = 3;
            key_id_lbl.Text = "Key ID:";
            // 
            // modifiers_lbl
            // 
            modifiers_lbl.AutoSize = true;
            modifiers_lbl.Location = new Point(480, 22);
            modifiers_lbl.Name = "modifiers_lbl";
            modifiers_lbl.Size = new Size(60, 15);
            modifiers_lbl.TabIndex = 4;
            modifiers_lbl.Text = "Modifiers:";
            // 
            // modifierID
            // 
            modifierID.Location = new Point(546, 19);
            modifierID.Name = "modifierID";
            modifierID.Size = new Size(73, 23);
            modifierID.TabIndex = 5;
            // 
            // copy_btn
            // 
            copy_btn.Location = new Point(635, 19);
            copy_btn.Name = "copy_btn";
            copy_btn.Size = new Size(54, 23);
            copy_btn.TabIndex = 6;
            copy_btn.Text = "Copy";
            copy_btn.UseVisualStyleBackColor = true;
            copy_btn.Click += copy_btn_Click;
            // 
            // combination_view
            // 
            combination_view.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left;
            combination_view.Location = new Point(25, 71);
            combination_view.Name = "combination_view";
            combination_view.Size = new Size(664, 139);
            combination_view.TabIndex = 8;
            combination_view.UseCompatibleStateImageBehavior = false;
            // 
            // HiddenWin
            // 
            AutoScaleDimensions = new SizeF(7F, 15F);
            AutoScaleMode = AutoScaleMode.Font;
            ClientSize = new Size(714, 234);
            Controls.Add(combination_view);
            Controls.Add(copy_btn);
            Controls.Add(modifierID);
            Controls.Add(modifiers_lbl);
            Controls.Add(key_id_lbl);
            Controls.Add(keyID);
            Controls.Add(keyLabel);
            Controls.Add(keyRevealer);
            Name = "HiddenWin";
            Text = "Keyboard Hotkeys";
            ResumeLayout(false);
            PerformLayout();
        }

        #endregion

        private TextBox keyRevealer;
        private Label keyLabel;
        private TextBox keyID;
        private Label key_id_lbl;
        private Label modifiers_lbl;
        private TextBox modifierID;
        private Button copy_btn;
        private ListView combination_view;
    }
}
