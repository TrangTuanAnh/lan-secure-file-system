using frontend.Models;
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace frontend.ViewModels
{
    public class RoomViewModel
    {
        public int RoomId { get; set; } 

        public string RoomName { get; set; }
        public string Role { get; set; }

        public ObservableCollection<Member> Members { get; set; }
        public ObservableCollection<FileItem> Files { get; set; }
    }
}
