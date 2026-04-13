using frontend.Models;
using frontend.ViewModels;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace frontend.Services
{
    internal class FakeAPIServices
    {
        // ===== HOME =====
        public List<Room> GetRooms()
        {
            return new List<Room>
            {
                new Room { Id = 1, Name = "Security Team", MemberCount = 5 },
                new Room { Id = 2, Name = "Dev Team", MemberCount = 2 }
            };
        }

        public List<TaskItem> GetRecentTasks()
        {
            return new List<TaskItem>
            {
                new TaskItem { FileName = "report.pdf", RoomName = "Security Team", Time = "2 min ago" },
                new TaskItem { FileName = "data.zip", RoomName = "Dev Team", Time = "5 min ago" },
                new TaskItem { FileName = "image.png", RoomName = "DevOps", Time = "10 min ago" }
            };
        }

        // ===== ROOM DETAIL =====
        public RoomViewModel GetRoomDetail(int roomId)
        {
            if (roomId == 1)
            {
                return new RoomViewModel
                {
                    RoomId = 1,
                    RoomName = "Security Team",
                    Role = "OWNER",
                    Members = new ObservableCollection<Member>
                    {
                        new Member { Username = "Khang", Role = "OWNER" },
                        new Member { Username = "An", Role = "USER" },
                        new Member { Username = "Binh", Role = "USER" },
                        new Member { Username = "Chau", Role = "USER" },
                        new Member { Username = "Dung", Role = "USER" }
                    },
                    Files = new ObservableCollection<FileItem>
                    {
                        new FileItem { Name = "report.pdf", Size = "2MB", Uploader = "Khang", Time = "10:00" },
                        new FileItem { Name = "data.zip", Size = "5MB", Uploader = "An", Time = "10:05" }
                    }
                };
            }

            // dev team
            return new RoomViewModel
            {
                RoomId = 2,
                RoomName = "Dev Team",
                Role = "USER",
                Members = new ObservableCollection<Member>
                {
                    new Member { Username = "Duc", Role = "OWNER" },
                    new Member { Username = "Minh", Role = "USER" }
                },
                Files = new ObservableCollection<FileItem>
                {
                    new FileItem { Name = "image.png", Size = "10MB", Uploader = "Duc", Time = "11:00" }
                }
            };
        }
    }
}
