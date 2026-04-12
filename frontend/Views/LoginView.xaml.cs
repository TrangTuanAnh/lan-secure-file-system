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
    /// Interaction logic for LoginView.xaml
    /// </summary>
    public partial class LoginView : Window
    {
        public LoginView()
        {
            InitializeComponent();
        }

        // 1. LOGIN
        private async void Login_Click(object sender, RoutedEventArgs e)
        {
            var auth = new AuthServices();

            var result = await auth.Login(txtUsername.Text, txtPassword.Password);

            if (result != null)
            {
                // lưu session
                App.Current.Properties["token"] = result.Token;
                App.Current.Properties["username"] = result.Username;

                // mở dashboard
                var dash = new DashboardView();
                dash.Show();

                this.Close();
            }
            else
            {
                MessageBox.Show("Sai tài khoản hoặc mật khẩu");
            }
        }

        // 2. qua SIGNUP
        private void Signup_Click(object sender, System.Windows.Input.MouseButtonEventArgs e)
        {
            SignupView signup = new SignupView();
            signup.Show();
            this.Close();
        }

        // 3. qua FORGOT PASSWORD
        private void Forgot_Click(object sender, System.Windows.Input.MouseButtonEventArgs e)
        {
            ForgotPasswordView forgot = new ForgotPasswordView();
            forgot.Show();
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

    }
}
