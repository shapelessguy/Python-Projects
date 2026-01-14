namespace Timer
{
    partial class TimerWin
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
            timerFront = new DateTimePicker();
            overlay = new Label();
            notes = new TextBox();
            SuspendLayout();
            // 
            // timerFront
            // 
            timerFront.CalendarMonthBackground = SystemColors.InactiveCaptionText;
            timerFront.CustomFormat = "  HH:mm:ss";
            timerFront.Font = new Font("Microsoft Sans Serif", 36F, FontStyle.Bold, GraphicsUnit.Point, 0);
            timerFront.Format = DateTimePickerFormat.Custom;
            timerFront.Location = new Point(12, 17);
            timerFront.Margin = new Padding(4, 3, 4, 3);
            timerFront.Name = "timerFront";
            timerFront.ShowUpDown = true;
            timerFront.Size = new Size(265, 62);
            timerFront.TabIndex = 0;
            timerFront.Value = new DateTime(2019, 7, 21, 0, 0, 0, 0);
            // 
            // overlay
            // 
            overlay.BackColor = Color.FromArgb(24, 24, 24);
            overlay.Font = new Font("Microsoft Sans Serif", 36F, FontStyle.Bold, GraphicsUnit.Point, 0);
            overlay.ForeColor = SystemColors.ButtonFace;
            overlay.Location = new Point(5, 16);
            overlay.Margin = new Padding(4, 0, 4, 0);
            overlay.Name = "overlay";
            overlay.Size = new Size(274, 63);
            overlay.TabIndex = 1;
            overlay.Text = "00:00:00";
            overlay.TextAlign = ContentAlignment.MiddleCenter;
            overlay.Visible = false;
            // 
            // notes
            // 
            notes.BackColor = Color.FromArgb(24, 24, 24);
            notes.BorderStyle = BorderStyle.FixedSingle;
            notes.Font = new Font("Microsoft Sans Serif", 9.75F, FontStyle.Bold, GraphicsUnit.Point, 0);
            notes.ForeColor = Color.White;
            notes.Location = new Point(14, 90);
            notes.Margin = new Padding(4, 3, 4, 3);
            notes.Name = "notes";
            notes.Size = new Size(263, 22);
            notes.TabIndex = 2;
            // 
            // TimerWin
            // 
            AutoScaleDimensions = new SizeF(7F, 15F);
            AutoScaleMode = AutoScaleMode.Font;
            BackColor = Color.FromArgb(24, 24, 24);
            ClientSize = new Size(290, 122);
            Controls.Add(notes);
            Controls.Add(timerFront);
            Controls.Add(overlay);
            ForeColor = SystemColors.ControlText;
            FormBorderStyle = FormBorderStyle.FixedSingle;
            Margin = new Padding(4, 3, 4, 3);
            Name = "TimerWin";
            ShowInTaskbar = false;
            StartPosition = FormStartPosition.CenterScreen;
            Text = "Timer";
            ResumeLayout(false);
            PerformLayout();

        }

        private System.Windows.Forms.DateTimePicker timerFront;
        private System.Windows.Forms.Label overlay;
        private System.Windows.Forms.TextBox notes;

        #endregion
    }
}
