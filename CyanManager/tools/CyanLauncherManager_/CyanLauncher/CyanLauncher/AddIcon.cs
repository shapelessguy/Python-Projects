using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace CyanLauncher
{
    public partial class AddIcon : Form
    {
        public string imagePath = "";
        public Icon edit = null;
        public int icon_index = -1;
        public static bool active = false;
        public AddIcon(Icon edit = null, int icon_index=-1)
        {
            this.edit = edit;
            this.icon_index = icon_index;
            active = true;
            InitializeComponent();
            if (edit != null) button1.Text = "Edit";
            changePathColor(); 
            setCheckBox(true);
            changeButtonColor();
            Console.WriteLine(checkBox1.ForeColor);
        }

        private void pictureBox1_Click(object sender, EventArgs e)
        {
            OpenFileDialog dialog = new OpenFileDialog();
            dialog.InitialDirectory = Properties.Settings.Default.lastImgPath;
            string filter = "All Files|*.*|Bitmap Image (.bmp)|*.bmp|Gif Image (.gif)|*.gif|JPG Image (.jpg)|*.jpeg|JPEG Image (.jpeg)|*.jpeg|Png Image (.png)|*.png|Tiff Image (.tiff)|*.tiff|Wmf Image (.wmf)|*.wmf";
            dialog.Filter = filter;

            dialog.CheckFileExists = true;
            dialog.Multiselect = false;

            if (dialog.ShowDialog() == DialogResult.OK)
            {
                try
                {
                    Properties.Settings.Default.lastImgPath = Directory.GetParent(dialog.FileName).FullName;
                    Program.Save();
                    imagePath = dialog.FileName;
                    pictureBox1.Image = Bitmap.FromFile(dialog.FileName); 
                    changeButtonColor();
                }
                catch (Exception) { }
            }
        }

        private string GenerateCausualString(int length)
        {
            Random random = new Random();
            const string chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
            return new string(Enumerable.Repeat(chars, length).Select(s => s[random.Next(s.Length)]).ToArray());
        }
        private void button1_Click(object sender, EventArgs e)
        {
            bool valid = checkValidity(true);
            if (!valid) return;

            if (Path.GetFullPath(imagePath) != Program.iconsFolder)
            {
                string destFile = Program.iconsFolder + @"\" + GenerateCausualString(10) + Path.GetExtension(imagePath);
                File.Copy(imagePath, destFile);
                imagePath = destFile;
            }

            string as_admin = "true";
            if (!checkBox1.Checked && checkBox1.AutoCheck) as_admin = "false";
            Icon icon = new Icon(textBox1.Text, textBox2.Text, imagePath, as_admin);
            Program.frontal.AddIcon_(icon, edit);
            Console.WriteLine("New icon added");
            try
            {
                Close();
            }
            catch (Exception) { }
        }

        private void label1_Click(object sender, EventArgs e)
        {
            OpenFileDialog dialog = new OpenFileDialog();
            dialog.InitialDirectory = Directory.GetParent(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86)).FullName;
            string filter = "All Files|*.*|File (.exe)|*.exe";
            dialog.Filter = filter;
            dialog.DereferenceLinks = false;

            dialog.CheckFileExists = true;
            dialog.Multiselect = false;
            if (dialog.ShowDialog() == DialogResult.OK)
            {
                if(Path.GetExtension(dialog.FileName) == ".exe" || Path.GetExtension(dialog.FileName).Equals(".lnk"))
                {
                    try
                    {
                        textBox1.Text = dialog.FileName;
                    }
                    catch (Exception) { }
                }
            }
        }

        private void AddIcon_FormClosed(object sender, FormClosedEventArgs e)
        {
            active = false;
        }

        private bool checkValidity(bool showMessage = false)
        {
            bool output = true;
            string errors = "";
            if (textBox2.Text.Length > 23)
            {
                string message = "The application/folder name must contain less then 24 characters";
                if (showMessage) MessageBox.Show(message);
                errors += message + ", ";
                output = false;
            }
            if (!File.Exists(textBox1.Text) && !Directory.Exists(textBox1.Text))
            {
                string message = textBox1.Text + " application/folder doesn't exist!";
                if (showMessage) MessageBox.Show(message);
                errors += message + ", ";
                output = false;
            }
            if (textBox1.Text == "" || textBox2.Text == "" || imagePath == "")
            {
                string message = "Please fill out every field in this form.";
                if (showMessage) MessageBox.Show(message);
                errors += message + ", ";
                output = false;
            }
            int i = 0;
            foreach (Info inf in Program.INFO)
            {
                if (edit != null && i == icon_index) continue;
                if (textBox1.Text == inf.exepath)
                {
                    string message = "Application/folder already in the catalogue!";
                    if (showMessage) MessageBox.Show(message);
                    errors += message + ", ";
                    output = false;
                }
                i++;
            }
            Console.WriteLine(errors);
            return output;
        }

        private void changeButtonColor()
        {
            bool valid = checkValidity();
            if (valid) button1.BackColor = Color.Green;
            else button1.BackColor = Color.DarkRed;
        }

        private void setCheckBox(bool state)
        {
            if (state)
            {
                checkBox1.FlatStyle = FlatStyle.Standard;
                checkBox1.ForeColor = Color.White;
                checkBox1.AutoCheck = true;
            }
            else
            {
                checkBox1.AutoCheck = false;
                checkBox1.Checked = false;
                checkBox1.FlatStyle = FlatStyle.Flat;
                checkBox1.ForeColor = Color.Gray;
            }
        }

        private void changePathColor()
        {
            if (File.Exists(textBox1.Text) || Directory.Exists(textBox1.Text))
            {
                label1.ForeColor = Color.Green;
                if (Path.GetExtension(textBox1.Text) == ".lnk") { setCheckBox(false); }
                else setCheckBox(true);
            }
            else if (textBox1.Text == "")
            {
                label1.ForeColor = Color.LightSeaGreen;
                setCheckBox(true);
            }
            else
            {
                label1.ForeColor = Color.Red;
                setCheckBox(false);
            }
        }

        private void textBox1_TextChanged(object sender, EventArgs e)
        {
            changeButtonColor();
            changePathColor();
        }

        private void textBox2_TextChanged(object sender, EventArgs e)
        {
            changeButtonColor();
        }

    }
}
