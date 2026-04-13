using frontend.Models;
using frontend.Services;
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
        private RoomViewModel lastRoom;

        public DashboardView()
        {
            InitializeComponent();
            //MainContent.Content = new HomePage();
            DataContext = new HomeViewModel();

            MainContent.Content = new HomePage();
            SetActiveTab("home");
            ShowRecent(true);
        }

        public void OpenRoom(Room room)
        {
            var api = new FakeAPIServices();

            var roomVM = api.GetRoomDetail(room.Id);

            MainContent.Content = new RoomPage(roomVM);

            SetActiveTab("recent");
            ShowRecent(false);
        }

        public void SetActiveTab(string tab)
        {
            var active = new SolidColorBrush(Color.FromRgb(47, 42, 74));

            HomeTab.Background = tab == "home" ? active : Brushes.Transparent;
            RecentTab.Background = tab == "recent" ? active : Brushes.Transparent;
        }

        public void ShowRecent(bool show)
        {
            RecentPanel.Visibility = show ? Visibility.Visible : Visibility.Collapsed;
        }
        private void HomeTab_Click(object sender, System.Windows.Input.MouseButtonEventArgs e)
        {
            MainContent.Content = new HomePage();
            SetActiveTab("home");
            ShowRecent(true);
        }

        private void RecentTab_Click(object sender, MouseButtonEventArgs e)
        {
            if (lastRoom != null)
            {
                MainContent.Content = new RoomPage(lastRoom);
                SetActiveTab("recent");
                ShowRecent(false);
            }
        }
    }
}
