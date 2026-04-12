using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;

namespace frontend.Services
{
    internal class AuthServices
    {
        private readonly HttpClient _http = new HttpClient
        {
            BaseAddress = new Uri("http://localhost:5000") // sửa sau
        };

        // LOGIN

        public async Task<LoginResponse?> Login(string username, string password)
        {
            // ===== FAKE MODE =====
            if (username == "admin" && password == "123")
            {
                return new LoginResponse
                {
                    Token = "fake-token",
                    Username = username
                };
            }

            return null;

            // ===== REAL MODE (bật khi có backend) =====
            /*
            var res = await _http.PostAsJsonAsync("/api/auth/login", new
            {
                username,
                password
            });

            if (!res.IsSuccessStatusCode)
                return null;

            return await res.Content.ReadFromJsonAsync<LoginResponse>();
            */
        }

        // SIGN UP
        public async Task<bool> Signup(string username, string password)
        {
            // ===== FAKE MODE =====
            if (!string.IsNullOrWhiteSpace(username) && !string.IsNullOrWhiteSpace(password))
                return true;

            return false;

            // ===== REAL MODE =====
            /*
            var res = await _http.PostAsJsonAsync("/api/auth/signup", new
            {
                username,
                password
            });

            return res.IsSuccessStatusCode;
            */
        }

        public async Task<bool> ResetPassword(string email)
        {
            // FAKE MODE
            if (!string.IsNullOrWhiteSpace(email))
                return true;

            return false;

            // REAL MODE
            /*
            var res = await _http.PostAsJsonAsync("/api/auth/reset-password", new
            {
                email
            });

            return res.IsSuccessStatusCode;
            */
        }
    }

    public class LoginResponse
    {
        public string Token { get; set; }
        public string Username { get; set; }

    }
}
