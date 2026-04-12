using frontend.ViewModels;
using frontend.Views.Pages;
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
using System.Windows.Threading;

namespace frontend.Views
{
    /// <summary>
    /// Interaction logic for Dashboard.xaml
    /// </summary>
    public partial class DashboardView : Window
    {
        //private DispatcherTimer timer;

        public DashboardView()
        {
            InitializeComponent();
            MainContent.Content = new HomePage();
            DataContext = new HomeViewModel();
            //timer = new DispatcherTimer();
            //timer.Interval = TimeSpan.FromSeconds(1);
            //timer.Tick += Timer_Tick;
            //timer.Start();
        }

        //private void Timer_Tick(object sender, EventArgs e)
        //{
        //    CurrentTimeText.Text = DateTime.Now.ToString("HH:mm:ss - dd/MM/yyyy");
        //}
    }
}
