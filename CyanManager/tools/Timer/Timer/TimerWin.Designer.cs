namespace Timer
{
    partial class TimerWin
    {
        private System.ComponentModel.IContainer components = null!;

        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        // The window is drawn in code (TimerWin.cs): nothing for the designer to lay out.
        private void InitializeComponent()
        {
            components = new System.ComponentModel.Container();
            SuspendLayout();
            AutoScaleMode = AutoScaleMode.Dpi;
            AutoScaleDimensions = new SizeF(96F, 96F);
            Name = "TimerWin";
            Text = "Timer";
            ResumeLayout(false);
        }
    }
}
