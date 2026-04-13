using frontend.Models;
using frontend.ViewModels;
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

namespace frontend.Views.Pages
{
    /// <summary>
    /// Interaction logic for HomePage.xaml
    /// </summary>
    public partial class HomePage : UserControl
    {
        public HomePage()
        {
            InitializeComponent();
            DataContext = new ViewModels.HomeViewModel();
        }

        private void Room_Click(object sender, RoutedEventArgs e)
        {
            var button = sender as Button;
            var room = button?.DataContext as Room;

            if (room == null) return;

            var dash = Window.GetWindow(this) as DashboardView;
            if (dash == null) return;

            dash.OpenRoom(room);
        }
    }
}
