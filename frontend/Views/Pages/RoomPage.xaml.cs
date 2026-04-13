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
    /// Interaction logic for Window1.xaml
    /// </summary>
    public partial class RoomPage : UserControl
    {
        public RoomPage(RoomViewModel vm)
        {
            InitializeComponent();
            DataContext = vm;
        }

        private void Room_Click(object sender, MouseButtonEventArgs e)
        {
            var border = sender as Border;
            var room = border?.DataContext as RoomViewModel;

            if (room == null) return;

            var dash = (DashboardView)Application.Current.MainWindow;
        }
    }
}
