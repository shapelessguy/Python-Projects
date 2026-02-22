namespace Notifications
{
    partial class NotificationForm
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
            icon = new PictureBox();
            ((System.ComponentModel.ISupportInitialize)icon).BeginInit();
            SuspendLayout();
            // 
            // icon
            // 
            icon.Location = new Point(12, 12);
            icon.Name = "icon";
            icon.Size = new Size(100, 100);
            icon.SizeMode = PictureBoxSizeMode.StretchImage;
            icon.TabIndex = 1;
            icon.TabStop = false;
            // 
            // NotificationForm
            // 
            AutoScaleDimensions = new SizeF(7F, 15F);
            AutoScaleMode = AutoScaleMode.Font;
            BackColor = Color.White;
            ClientSize = new Size(1677, 126);
            ControlBox = false;
            Controls.Add(icon);
            ForeColor = SystemColors.ControlText;
            FormBorderStyle = FormBorderStyle.None;
            Name = "NotificationForm";
            ShowIcon = false;
            ShowInTaskbar = false;
            Text = "Form1";
            TransparencyKey = Color.White;
            ((System.ComponentModel.ISupportInitialize)icon).EndInit();
            ResumeLayout(false);
        }

        #endregion

        private PictureBox icon;
    }
}
