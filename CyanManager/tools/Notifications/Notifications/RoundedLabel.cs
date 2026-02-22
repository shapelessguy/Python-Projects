using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.Windows.Forms;

public class RoundedLabel : Label
{
    private readonly int CornerRadius = 18;
    private readonly Color FillColor = Color.FromArgb(0, 120, 215);
    private readonly Color BorderColor = Color.Black;
    private readonly int BorderWidth = 3;
    private readonly int PaddingLeft = 30;
    private readonly int PaddingRight = 30;
    private readonly int PaddingTop = 12;
    private readonly int PaddingBottom = 12;

    public RoundedLabel()
    {
        SetStyle(
            ControlStyles.SupportsTransparentBackColor |
            ControlStyles.UserPaint |
            ControlStyles.AllPaintingInWmPaint |
            ControlStyles.OptimizedDoubleBuffer |
            ControlStyles.ResizeRedraw,
            true);

        BackColor = Color.Transparent;
        DoubleBuffered = true;

        ForeColor = Color.White;
        Font = new Font("Modern No. 20", 24f, FontStyle.Bold, GraphicsUnit.Point);
        TextAlign = ContentAlignment.MiddleCenter;
    }

    protected override void OnPaint(PaintEventArgs e)
    {
        e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
        e.Graphics.InterpolationMode = InterpolationMode.HighQualityBicubic;  // ← this helps curves
        e.Graphics.PixelOffsetMode = PixelOffsetMode.HighQuality;           // ← add this too
        e.Graphics.CompositingQuality = CompositingQuality.HighQuality;        // ← optional but good

        float borderHalf = BorderWidth / 2f;
        float margin = borderHalf + 2f;  // extra 2px buffer usually fixes most jaggedness

        RectangleF drawRect = new RectangleF(
            margin,
            margin,
            Width - margin * 2 - 1,
            Height - margin * 2 - 1);

        float adjustedRadius = Math.Max(1, CornerRadius - borderHalf);

        using (GraphicsPath path = GetRoundedRectangle(drawRect, adjustedRadius))
        {
            // Fill first
            using (var brush = new SolidBrush(FillColor))
            {
                e.Graphics.FillPath(brush, path);
            }

            // Border on top
            using (var pen = new Pen(BorderColor, BorderWidth))
            {
                pen.LineJoin = LineJoin.Round;     // crucial for smooth corners with thick pen
                pen.StartCap = LineCap.Round;      // helps open ends if any
                pen.EndCap = LineCap.Round;
                e.Graphics.DrawPath(pen, path);
            }
        }

        if (!string.IsNullOrWhiteSpace(Text))
        {
            var textRect = new Rectangle(
                PaddingLeft + (int)margin,
                PaddingTop + (int)margin,
                Width - PaddingLeft - PaddingRight - (int)(margin * 2),
                Height - PaddingTop - PaddingBottom - (int)(margin * 2));

            TextFormatFlags flags = TextFormatFlags.HorizontalCenter |
                                    TextFormatFlags.VerticalCenter |
                                    TextFormatFlags.WordBreak |
                                    TextFormatFlags.TextBoxControl;

            TextRenderer.DrawText(e.Graphics, Text, Font, textRect, ForeColor, flags);
        }
    }

    private GraphicsPath GetRoundedRectangle(RectangleF rect, float radius)
    {
        float diameter = radius * 2;
        var path = new GraphicsPath();

        // Top-left
        path.AddArc(rect.X, rect.Y, diameter, diameter, 180, 90);

        // Top-right
        path.AddArc(rect.Right - diameter, rect.Y, diameter, diameter, 270, 90);

        // Bottom-right
        path.AddArc(rect.Right - diameter, rect.Bottom - diameter, diameter, diameter, 0, 90);

        // Bottom-left
        path.AddArc(rect.X, rect.Bottom - diameter, diameter, diameter, 90, 90);

        path.CloseFigure();
        return path;
    }
}