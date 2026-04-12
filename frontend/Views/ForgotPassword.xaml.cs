using frontend.Services;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Documents;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Shapes;

namespace frontend.Views
{
    /// <summary>
    /// Interaction logic for ForgotPassword.xaml
    /// </summary>
    public partial class ForgotPasswordView : Window
    {
        public ForgotPasswordView()
        {
            InitializeComponent();
        }

        private async void Reset_Click(object sender, RoutedEventArgs e)
        {
            var auth = new AuthServices();

            var success = await auth.ResetPassword(txtEmail.Text);

            if (success)
            {
                MessageBox.Show("Đã gửi yêu cầu reset mật khẩu");
            }
            else
            {
                MessageBox.Show("Không tìm thấy tài khoản");
            }
        }

        private void BackToLogin_Click(object sender, System.Windows.Input.MouseButtonEventArgs e)
        {
            LoginView l = new LoginView();
            l.Show();
            this.Close();
        }

        private void Email_GotFocus(object sender, RoutedEventArgs e)
        {
            if (txtEmail.Text == "Email / Phone")
            {
                txtEmail.Text = "";
                txtEmail.Foreground = Brushes.White;
            }
        }

        private void Email_LostFocus(object sender, RoutedEventArgs e)
        {
            if (string.IsNullOrWhiteSpace(txtEmail.Text))
            {
                txtEmail.Text = "Email / Phone";
                txtEmail.Foreground = Brushes.Gray;
            }
        }
    }
}
