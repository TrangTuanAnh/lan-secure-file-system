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
    /// Interaction logic for SignupView.xaml
    /// </summary>
    public partial class SignupView : Window
    {
        public SignupView()
        {
            InitializeComponent();
        }

        private async void Signup_Click(object sender, RoutedEventArgs e)
        {
            var username = txtUsername.Text;
            var email = txtEmail.Text;
            var password = txtPassword.Password;
            var confirmPassword = txtConfirmPassword.Password;

            // ===== VALIDATE =====

            if (string.IsNullOrWhiteSpace(username) ||
                string.IsNullOrWhiteSpace(email) ||
                string.IsNullOrWhiteSpace(password))
            {
                MessageBox.Show("Vui lòng nhập đầy đủ thông tin");
                return;
            }

            if (password != confirmPassword)
            {
                MessageBox.Show("Mật khẩu xác nhận không khớp");
                return;
            }

            if (password.Length < 6)
            {
                MessageBox.Show("Mật khẩu phải >= 6 ký tự");
                return;
            }

            // ===== CALL API =====

            var auth = new AuthServices();
            var success = await auth.Signup(username, password, email);

            if (success)
            {
                MessageBox.Show("Đăng ký thành công");

                var login = new LoginView();
                login.Show();
                this.Close();
            }
            else
            {
                MessageBox.Show("Đăng ký thất bại");
            }
        }

        private void BackToLogin_Click(object sender, System.Windows.Input.MouseButtonEventArgs e)
        {
            LoginView l = new LoginView();
            l.Show();
            this.Close();
        }

        private void Username_GotFocus(object sender, RoutedEventArgs e)
        {
            if (txtUsername.Text == "Username")
            {
                txtUsername.Text = "";
                txtUsername.Foreground = Brushes.White;
            }
        }

        private void Username_LostFocus(object sender, RoutedEventArgs e)
        {
            if (string.IsNullOrWhiteSpace(txtUsername.Text))
            {
                txtUsername.Text = "Username";
                txtUsername.Foreground = Brushes.Gray;
            }
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

        private void Password_GotFocus(object sender, RoutedEventArgs e)
        {
            txtPasswordPlaceholder.Visibility = Visibility.Collapsed;
        }

        private void Password_LostFocus(object sender, RoutedEventArgs e)
        {
            if (string.IsNullOrEmpty(txtPassword.Password))
            {
                txtPasswordPlaceholder.Visibility = Visibility.Visible;
            }
        }

        private void ConfirmPassword_GotFocus(object sender, RoutedEventArgs e)
        {
            txtConfirmPasswordPlaceholder.Visibility = Visibility.Collapsed;
        }

        private void ConfirmPassword_LostFocus(object sender, RoutedEventArgs e)
        {
            if (string.IsNullOrEmpty(txtConfirmPassword.Password))
            {
                txtConfirmPasswordPlaceholder.Visibility = Visibility.Visible;
            }
        }
    }
}
