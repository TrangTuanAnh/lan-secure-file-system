using frontend.Models;
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace frontend.Services
{
    internal class FakeAPIServices
    {
        public List<Room> GetRooms()
        {
            return new List<Room>
            {
                new Room { Name = "Security Team", FileCount = 12, MemberCount = 5 },
                new Room { Name = "Dev Team", FileCount = 10, MemberCount = 10 }
            };
        }

        public List<TaskItem> GetRecentTasks()
        {
            return new List<TaskItem>
            {
                new TaskItem { FileName = "report.pdf", RoomName = "Security", Time = "2 min ago" },
                new TaskItem { FileName = "data.zip", RoomName = "Backend", Time = "5 min ago" },
                new TaskItem { FileName = "image.png", RoomName = "DevOps", Time = "10 min ago" }
            };
        }
    }
}
