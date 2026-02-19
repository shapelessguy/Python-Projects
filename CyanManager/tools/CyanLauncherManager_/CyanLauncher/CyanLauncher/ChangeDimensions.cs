using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace CyanLauncher
{
    public partial class ChangeDimensions : Form
    {
        Frontal frontal = null;
        static public bool active = false;
        public ChangeDimensions(Frontal frontal)
        {
            this.frontal = frontal;
            InitializeComponent();
            active = true;
            dateTimePicker1.Value = new DateTime(2000, 1, 1, Program.dimensions.Width, 0, 0);
            dateTimePicker2.Value = new DateTime(2000, 1, 1, Program.dimensions.Height, 0, 0);
            trackBar1.Value = (Program.iconSize.Width - 80) / 20;
            trackBar2.Value = Program.opacity;
            checkBox1.Checked = Program.allowsDrag;
            checkBox2.Checked = Program.centerSpawn;
            checkBox3.Checked = Program.vanish;
            checkBox4.Checked = Program.canMove;

            dateTimePicker1.ValueChanged += new EventHandler(dateTimePicker1_ValueChanged);
            dateTimePicker2.ValueChanged += new EventHandler(dateTimePicker2_ValueChanged);
            trackBar1.ValueChanged += new EventHandler(trackBar1_ValueChanged);
            trackBar2.ValueChanged += new EventHandler(trackBar2_ValueChanged);
            checkBox1.CheckedChanged += new EventHandler(checkBox1_CheckedChanged);
            checkBox2.CheckedChanged += new EventHandler(checkBox2_CheckedChanged);
            checkBox3.CheckedChanged += new EventHandler(checkBox3_CheckedChanged);
            checkBox4.CheckedChanged += new EventHandler(checkBox4_CheckedChanged);
        }

        private void sizeChanged()
        {
            Size dim = new Size(dateTimePicker1.Value.Hour, dateTimePicker2.Value.Hour);
            Program.frontal.SetDimensions(dim);
            Program.allowsDrag = checkBox1.Checked;
        }

        private void trackBar1_ValueChanged(object sender, EventArgs e)
        {
            int point = 0;
            point = 80 + 20 * trackBar1.Value;
            Program.iconSize = new Size(point, point);
            Size dim = new Size(Program.dimensions.Width, Program.dimensions.Height);
            Program.frontal.SetDimensions(dim);
            Program.frontal.IconResize();
        }

        private void trackBar2_ValueChanged(object sender, EventArgs e)
        {
            Program.opacity = trackBar2.Value;
            frontal.setOpacity(Program.opacity);
            Program.saveSettings();
        }

        private void checkBox1_CheckedChanged(object sender, EventArgs e)
        {
            Program.allowsDrag = checkBox1.Checked;
            Program.saveSettings();
            Program.frontal.Drag();
        }
        private void checkBox2_CheckedChanged(object sender, EventArgs e)
        {
            Program.centerSpawn = checkBox2.Checked;
            Program.saveSettings();
        }
        private void checkBox3_CheckedChanged(object sender, EventArgs e)
        {
            Program.vanish = checkBox3.Checked;
            Program.saveSettings();
        }
        private void checkBox4_CheckedChanged(object sender, EventArgs e)
        {
            Program.canMove = checkBox4.Checked;
            Program.saveSettings();
        }

        private void dateTimePicker1_ValueChanged(object sender, EventArgs e)
        {
            sizeChanged();
            Program.saveSettings();
        }

        private void dateTimePicker2_ValueChanged(object sender, EventArgs e)
        {
            sizeChanged();
            Program.saveSettings();
        }

        private void ChangeDimensions_FormClosed(object sender, FormClosedEventArgs e)
        {
            active = false;
        }
    }
}
