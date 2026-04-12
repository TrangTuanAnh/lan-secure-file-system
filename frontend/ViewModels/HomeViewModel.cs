using frontend.Models;
using frontend.Services;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace frontend.ViewModels
{
    internal class HomeViewModel
    {
        public List<Room> Rooms { get; set; }
        public List<TaskItem> RecentTasks { get; set; }

        public HomeViewModel()
        {
            var api = new Services.FakeAPIServices();
            Rooms = api.GetRooms();
            RecentTasks = api.GetRecentTasks();
        }
    }
}
