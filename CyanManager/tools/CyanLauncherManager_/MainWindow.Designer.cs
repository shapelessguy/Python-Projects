namespace CyanLauncherManager
{
    partial class MainWindow
    {
        /// <summary>
        /// Variabile di progettazione necessaria.
        /// </summary>
        private System.ComponentModel.IContainer components = null;

        /// <summary>
        /// Pulire le risorse in uso.
        /// </summary>
        /// <param name="disposing">ha valore true se le risorse gestite devono essere eliminate, false in caso contrario.</param>
        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        #region Codice generato da Progettazione Windows Form

        /// <summary>
        /// Metodo necessario per il supporto della finestra di progettazione. Non modificare
        /// il contenuto del metodo con l'editor di codice.
        /// </summary>
        private void InitializeComponent()
        {
            System.ComponentModel.ComponentResourceManager resources = new System.ComponentModel.ComponentResourceManager(typeof(MainWindow));
            this.application_panel = new System.Windows.Forms.Panel();
            this.app_panel = new System.Windows.Forms.Panel();
            this.app_start = new System.Windows.Forms.Button();
            this.app_name = new System.Windows.Forms.TextBox();
            this.app_delete = new System.Windows.Forms.Button();
            this.app_picture = new System.Windows.Forms.PictureBox();
            this.function_panel = new System.Windows.Forms.Panel();
            this.panel1 = new System.Windows.Forms.Panel();
            this.newapp_add = new System.Windows.Forms.Button();
            this.newapp_name = new System.Windows.Forms.TextBox();
            this.newapp_picture = new System.Windows.Forms.PictureBox();
            this.update_btn = new System.Windows.Forms.Button();
            this.startup_check = new System.Windows.Forms.CheckBox();
            this.application_panel.SuspendLayout();
            this.app_panel.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)(this.app_picture)).BeginInit();
            this.function_panel.SuspendLayout();
            this.panel1.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)(this.newapp_picture)).BeginInit();
            this.SuspendLayout();
            // 
            // application_panel
            // 
            this.application_panel.Anchor = ((System.Windows.Forms.AnchorStyles)((((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Bottom) 
            | System.Windows.Forms.AnchorStyles.Left) 
            | System.Windows.Forms.AnchorStyles.Right)));
            this.application_panel.AutoScroll = true;
            this.application_panel.BackColor = System.Drawing.Color.Black;
            this.application_panel.Controls.Add(this.app_panel);
            this.application_panel.Location = new System.Drawing.Point(12, 128);
            this.application_panel.Name = "application_panel";
            this.application_panel.Size = new System.Drawing.Size(731, 320);
            this.application_panel.TabIndex = 0;
            // 
            // app_panel
            // 
            this.app_panel.Anchor = ((System.Windows.Forms.AnchorStyles)(((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Left) 
            | System.Windows.Forms.AnchorStyles.Right)));
            this.app_panel.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(7)))), ((int)(((byte)(7)))), ((int)(((byte)(7)))));
            this.app_panel.Controls.Add(this.app_start);
            this.app_panel.Controls.Add(this.app_name);
            this.app_panel.Controls.Add(this.app_delete);
            this.app_panel.Controls.Add(this.app_picture);
            this.app_panel.ForeColor = System.Drawing.Color.FromArgb(((int)(((byte)(14)))), ((int)(((byte)(14)))), ((int)(((byte)(14)))));
            this.app_panel.Location = new System.Drawing.Point(8, 9);
            this.app_panel.Name = "app_panel";
            this.app_panel.Size = new System.Drawing.Size(700, 57);
            this.app_panel.TabIndex = 2;
            // 
            // app_start
            // 
            this.app_start.BackColor = System.Drawing.Color.Green;
            this.app_start.FlatAppearance.BorderColor = System.Drawing.Color.Maroon;
            this.app_start.FlatAppearance.BorderSize = 12;
            this.app_start.FlatAppearance.MouseDownBackColor = System.Drawing.Color.FromArgb(((int)(((byte)(64)))), ((int)(((byte)(0)))), ((int)(((byte)(0)))));
            this.app_start.FlatAppearance.MouseOverBackColor = System.Drawing.Color.Red;
            this.app_start.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.app_start.Font = new System.Drawing.Font("Constantia", 9.75F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(0)));
            this.app_start.Location = new System.Drawing.Point(14, 17);
            this.app_start.Name = "app_start";
            this.app_start.Size = new System.Drawing.Size(68, 23);
            this.app_start.TabIndex = 4;
            this.app_start.TabStop = false;
            this.app_start.Text = "Start";
            this.app_start.UseVisualStyleBackColor = false;
            // 
            // app_name
            // 
            this.app_name.AccessibleRole = System.Windows.Forms.AccessibleRole.None;
            this.app_name.Anchor = ((System.Windows.Forms.AnchorStyles)(((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Left) 
            | System.Windows.Forms.AnchorStyles.Right)));
            this.app_name.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(7)))), ((int)(((byte)(7)))), ((int)(((byte)(7)))));
            this.app_name.BorderStyle = System.Windows.Forms.BorderStyle.None;
            this.app_name.Cursor = System.Windows.Forms.Cursors.Default;
            this.app_name.Font = new System.Drawing.Font("Modern No. 20", 15.75F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(0)));
            this.app_name.ForeColor = System.Drawing.Color.White;
            this.app_name.ImeMode = System.Windows.Forms.ImeMode.NoControl;
            this.app_name.Location = new System.Drawing.Point(146, 17);
            this.app_name.Name = "app_name";
            this.app_name.ReadOnly = true;
            this.app_name.Size = new System.Drawing.Size(477, 23);
            this.app_name.TabIndex = 3;
            this.app_name.Text = "Default title";
            this.app_name.WordWrap = false;
            // 
            // app_delete
            // 
            this.app_delete.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.app_delete.BackColor = System.Drawing.Color.Red;
            this.app_delete.FlatAppearance.BorderColor = System.Drawing.Color.Maroon;
            this.app_delete.FlatAppearance.BorderSize = 12;
            this.app_delete.FlatAppearance.MouseDownBackColor = System.Drawing.Color.FromArgb(((int)(((byte)(64)))), ((int)(((byte)(0)))), ((int)(((byte)(0)))));
            this.app_delete.FlatAppearance.MouseOverBackColor = System.Drawing.Color.Red;
            this.app_delete.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.app_delete.Font = new System.Drawing.Font("Constantia", 9.75F, System.Drawing.FontStyle.Bold);
            this.app_delete.Location = new System.Drawing.Point(632, 17);
            this.app_delete.Name = "app_delete";
            this.app_delete.Size = new System.Drawing.Size(56, 23);
            this.app_delete.TabIndex = 2;
            this.app_delete.Text = "Delete";
            this.app_delete.UseVisualStyleBackColor = false;
            // 
            // app_picture
            // 
            this.app_picture.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(7)))), ((int)(((byte)(7)))), ((int)(((byte)(7)))));
            this.app_picture.Image = global::CyanLauncherManager.Properties.Resources.Icon;
            this.app_picture.Location = new System.Drawing.Point(94, 6);
            this.app_picture.Name = "app_picture";
            this.app_picture.Size = new System.Drawing.Size(45, 45);
            this.app_picture.SizeMode = System.Windows.Forms.PictureBoxSizeMode.StretchImage;
            this.app_picture.TabIndex = 0;
            this.app_picture.TabStop = false;
            // 
            // function_panel
            // 
            this.function_panel.Anchor = ((System.Windows.Forms.AnchorStyles)(((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Left) 
            | System.Windows.Forms.AnchorStyles.Right)));
            this.function_panel.BackColor = System.Drawing.Color.Black;
            this.function_panel.Controls.Add(this.panel1);
            this.function_panel.Location = new System.Drawing.Point(12, 12);
            this.function_panel.Name = "function_panel";
            this.function_panel.Size = new System.Drawing.Size(731, 67);
            this.function_panel.TabIndex = 1;
            // 
            // panel1
            // 
            this.panel1.Anchor = ((System.Windows.Forms.AnchorStyles)(((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Left) 
            | System.Windows.Forms.AnchorStyles.Right)));
            this.panel1.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(7)))), ((int)(((byte)(7)))), ((int)(((byte)(7)))));
            this.panel1.Controls.Add(this.newapp_add);
            this.panel1.Controls.Add(this.newapp_name);
            this.panel1.Controls.Add(this.newapp_picture);
            this.panel1.ForeColor = System.Drawing.Color.FromArgb(((int)(((byte)(14)))), ((int)(((byte)(14)))), ((int)(((byte)(14)))));
            this.panel1.Location = new System.Drawing.Point(3, 3);
            this.panel1.Name = "panel1";
            this.panel1.Size = new System.Drawing.Size(705, 57);
            this.panel1.TabIndex = 3;
            // 
            // newapp_add
            // 
            this.newapp_add.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.newapp_add.BackColor = System.Drawing.Color.Gray;
            this.newapp_add.FlatAppearance.BorderColor = System.Drawing.Color.Maroon;
            this.newapp_add.FlatAppearance.BorderSize = 12;
            this.newapp_add.FlatAppearance.MouseDownBackColor = System.Drawing.Color.FromArgb(((int)(((byte)(64)))), ((int)(((byte)(0)))), ((int)(((byte)(0)))));
            this.newapp_add.FlatAppearance.MouseOverBackColor = System.Drawing.Color.Red;
            this.newapp_add.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.newapp_add.Font = new System.Drawing.Font("Constantia", 12F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(0)));
            this.newapp_add.Location = new System.Drawing.Point(602, 14);
            this.newapp_add.Name = "newapp_add";
            this.newapp_add.Size = new System.Drawing.Size(75, 28);
            this.newapp_add.TabIndex = 5;
            this.newapp_add.Text = "ADD";
            this.newapp_add.UseVisualStyleBackColor = false;
            this.newapp_add.Click += new System.EventHandler(this.newapp_add_Click);
            // 
            // newapp_name
            // 
            this.newapp_name.AccessibleRole = System.Windows.Forms.AccessibleRole.None;
            this.newapp_name.Anchor = ((System.Windows.Forms.AnchorStyles)(((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Left) 
            | System.Windows.Forms.AnchorStyles.Right)));
            this.newapp_name.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(7)))), ((int)(((byte)(7)))), ((int)(((byte)(7)))));
            this.newapp_name.BorderStyle = System.Windows.Forms.BorderStyle.FixedSingle;
            this.newapp_name.Cursor = System.Windows.Forms.Cursors.IBeam;
            this.newapp_name.Font = new System.Drawing.Font("Modern No. 20", 15.75F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(0)));
            this.newapp_name.ForeColor = System.Drawing.Color.White;
            this.newapp_name.ImeMode = System.Windows.Forms.ImeMode.NoControl;
            this.newapp_name.Location = new System.Drawing.Point(69, 14);
            this.newapp_name.Name = "newapp_name";
            this.newapp_name.Size = new System.Drawing.Size(510, 30);
            this.newapp_name.TabIndex = 0;
            this.newapp_name.TabStop = false;
            this.newapp_name.WordWrap = false;
            this.newapp_name.KeyUp += new System.Windows.Forms.KeyEventHandler(this.newapp_name_KeyUp);
            // 
            // newapp_picture
            // 
            this.newapp_picture.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(7)))), ((int)(((byte)(7)))), ((int)(((byte)(7)))));
            this.newapp_picture.Image = global::CyanLauncherManager.Properties.Resources.Icon;
            this.newapp_picture.Location = new System.Drawing.Point(8, 6);
            this.newapp_picture.Name = "newapp_picture";
            this.newapp_picture.Size = new System.Drawing.Size(45, 45);
            this.newapp_picture.SizeMode = System.Windows.Forms.PictureBoxSizeMode.StretchImage;
            this.newapp_picture.TabIndex = 0;
            this.newapp_picture.TabStop = false;
            // 
            // update_btn
            // 
            this.update_btn.BackColor = System.Drawing.Color.PaleGreen;
            this.update_btn.FlatAppearance.BorderColor = System.Drawing.Color.Maroon;
            this.update_btn.FlatAppearance.BorderSize = 12;
            this.update_btn.FlatAppearance.MouseDownBackColor = System.Drawing.Color.FromArgb(((int)(((byte)(64)))), ((int)(((byte)(0)))), ((int)(((byte)(0)))));
            this.update_btn.FlatAppearance.MouseOverBackColor = System.Drawing.Color.Red;
            this.update_btn.FlatStyle = System.Windows.Forms.FlatStyle.Popup;
            this.update_btn.Font = new System.Drawing.Font("Constantia", 9.75F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(0)));
            this.update_btn.Location = new System.Drawing.Point(30, 92);
            this.update_btn.Name = "update_btn";
            this.update_btn.Size = new System.Drawing.Size(133, 23);
            this.update_btn.TabIndex = 5;
            this.update_btn.TabStop = false;
            this.update_btn.Text = "Update";
            this.update_btn.UseVisualStyleBackColor = false;
            this.update_btn.Click += new System.EventHandler(this.update_btn_Click);
            // 
            // startup_check
            // 
            this.startup_check.AutoSize = true;
            this.startup_check.Font = new System.Drawing.Font("Microsoft Sans Serif", 10F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(0)));
            this.startup_check.ForeColor = System.Drawing.SystemColors.ButtonHighlight;
            this.startup_check.Location = new System.Drawing.Point(640, 94);
            this.startup_check.Name = "startup_check";
            this.startup_check.Size = new System.Drawing.Size(80, 21);
            this.startup_check.TabIndex = 6;
            this.startup_check.Text = "Startup";
            this.startup_check.UseVisualStyleBackColor = true;
            this.startup_check.CheckedChanged += new System.EventHandler(this.checkBox1_CheckedChanged);
            // 
            // MainWindow
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 13F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.BackColor = System.Drawing.Color.Black;
            this.ClientSize = new System.Drawing.Size(756, 457);
            this.Controls.Add(this.startup_check);
            this.Controls.Add(this.update_btn);
            this.Controls.Add(this.function_panel);
            this.Controls.Add(this.application_panel);
            this.Icon = ((System.Drawing.Icon)(resources.GetObject("$this.Icon")));
            this.MinimumSize = new System.Drawing.Size(772, 324);
            this.Name = "MainWindow";
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterScreen;
            this.Text = "CyanLauncher Manager";
            this.FormClosing += new System.Windows.Forms.FormClosingEventHandler(this.MainWindow_FormClosing);
            this.application_panel.ResumeLayout(false);
            this.app_panel.ResumeLayout(false);
            this.app_panel.PerformLayout();
            ((System.ComponentModel.ISupportInitialize)(this.app_picture)).EndInit();
            this.function_panel.ResumeLayout(false);
            this.panel1.ResumeLayout(false);
            this.panel1.PerformLayout();
            ((System.ComponentModel.ISupportInitialize)(this.newapp_picture)).EndInit();
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion

        private System.Windows.Forms.Panel application_panel;
        private System.Windows.Forms.Panel function_panel;
        private System.Windows.Forms.Panel app_panel;
        private System.Windows.Forms.Button app_delete;
        private System.Windows.Forms.PictureBox app_picture;
        private System.Windows.Forms.TextBox app_name;
        private System.Windows.Forms.Button app_start;
        private System.Windows.Forms.Panel panel1;
        private System.Windows.Forms.Button newapp_add;
        private System.Windows.Forms.TextBox newapp_name;
        private System.Windows.Forms.PictureBox newapp_picture;
        private System.Windows.Forms.Button update_btn;
        private System.Windows.Forms.CheckBox startup_check;
    }
}

