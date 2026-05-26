# Giải thích chi tiết các Tools

  ---

  ## 1. 🤖 **Agent** (Tool: `Agent`)
  **Mô tả:** Khởi chạy một sub-agent độc lập để xử lý các tác vụ phức tạp, đa bước.

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `description` | string | ✅ | Mô tả ngắn 3-5 từ về tác vụ |
  | `prompt` | string | ✅ | Nội dung tác vụ giao cho agent |
  | `subagent_type` | string | ❌ | Loại agent chuyên biệt (`claude`, `Explore`, `general-purpose`, `Plan`, `statusline-setup`) |
  | `isolation` | string | ❌ | `"worktree"` để tạo git worktree riêng biệt |
  | `model` | string | ❌ | Override model (`sonnet`, `opus`, `haiku`) |
  | `run_in_background` | boolean | ❌ | Chạy nền, không chờ kết quả ngay |

  ### Cách sử dụng:
  ```
  Agent({
    description: "Tìm kiếm API endpoints",
    subagent_type: "Explore",
    prompt: "Tìm tất cả API endpoints trong thư mục src/routes/**"
  })
  ```

  ### Các loại sub-agent:
  - **`claude`**: Agent đa năng, có đầy đủ tools
  - **`Explore`**: Chỉ đọc, tìm kiếm file/code nhanh (không edit)
  - **`general-purpose`**: Nghiên cứu phức tạp, tìm kiếm nhiều bước
  - **`Plan`**: Thiết kế kiến trúc, lập kế hoạch implementation
  - **`statusline-setup`**: Cấu hình status line của Claude Code

  ### Use cases:
  - Chạy nhiều tác vụ song song (gửi cùng 1 message)
  - Nghiên cứu codebase mà không làm ô nhiễm context chính
  - Delegating code review, security audit
  - Tìm kiếm rộng trong codebase lớn

  ---

  ## 2. ❓ **AskUserQuestion**
  **Mô tả:** Hỏi user trong lúc thực thi để thu thập lựa chọn/yêu cầu.

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `questions` | array | ✅ | Danh sách câu hỏi (1-4 câu) |
  | `questions[].question` | string | ✅ | Nội dung câu hỏi |
  | `questions[].header` | string | ✅ | Nhãn ngắn (tối đa 12 ký tự) hiển thị dạng chip |
  | `questions[].options` | array | ✅ | Các lựa chọn (2-4 options) |
  | `questions[].multiSelect` | boolean | ❌ | Cho phép chọn nhiều đáp án |
  | `options[].label` | string | ✅ | Tên hiển thị của option |
  | `options[].description` | string | ✅ | Giải thích option |
  | `options[].preview` | string | ❌ | Preview content (code snippet, mockup) |

  ### Cách sử dụng:
  ```
  AskUserQuestion({
    questions: [{
      question: "Bạn muốn dùng framework nào?",
      header: "Framework",
      multiSelect: false,
      options: [
        { label: "React", description: "UI library phổ biến (Recommended)" },
        { label: "Vue", description: "Progressive framework" },
        { label: "Svelte", description: "Compiler-based framework" }
      ]
    }]
  })
  ```

  ### Use cases:
  - Làm rõ yêu cầu khi có nhiều hướng triển khai
  - Chọn thư viện, approach, design pattern
  - Thu thập user preferences trước khi code
  - **Trong Plan Mode**: Dùng để clarify TRƯỚC khi finalize plan (không dùng để hỏi "plan OK chưa?" — dùng `ExitPlanMode` cho việc đó)

  ---

  ## 3. 💻 **Bash**
  **Mô tả:** Thực thi lệnh bash trong terminal.

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `command` | string | ✅ | Lệnh bash cần chạy |
  | `description` | string | ✅ | Mô tả ngắn gọn lệnh làm gì |
  | `timeout` | number | ❌ | Timeout tính bằng ms (tối đa 600000ms = 10 phút) |
  | `run_in_background` | boolean | ❌ | Chạy nền, nhận notification khi xong |
  | `dangerouslyDisableSandbox` | boolean | ❌ | Tắt sandbox (cực kỳ nguy hiểm) |

  ### Cách sử dụng:
  ```
  Bash({ command: "npm test", description: "Chạy test suite" })
  Bash({ command: "npm run build", description: "Build project", run_in_background: true })
  Bash({ command: "git log --oneline -10", description: "Xem 10 commits gần nhất" })
  ```

  ### ⚠️ Lưu ý quan trọng:
  - **KHÔNG dùng** `find`, `grep`, `cat`, `head`, `tail` — dùng các tool chuyên biệt (Glob, Grep, Read)
  - Luôn dùng `&&` cho lệnh sequential, không dùng newlines
  - Không dùng `git -i` (interactive mode)
  - Không skip hooks (`--no-verify`)

  ### Use cases:
  - Chạy tests, build, install dependencies
  - Git operations (commit, status, diff)
  - Chạy scripts, CLI tools
  - Kiểm tra môi trường hệ thống

  ---

  ## 4. ⏰ **CronCreate**
  **Mô tả:** Tạo cron job để lên lịch chạy prompt theo thời gian.

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `cron` | string | ✅ | Biểu thức cron 5 trường (theo giờ local) |
  | `prompt` | string | ✅ | Prompt sẽ được enqueue khi cron kích hoạt |
  | `recurring` | boolean | ❌ | `true` = lặp lại (default), `false` = chạy 1 lần rồi xóa |
  | `durable` | boolean | ❌ | `true` = persist vào file, tồn tại qua session restart |

  ### Cú pháp cron:
  ```
  "* * * * *"
   │ │ │ │ └── Day of week (0-7, 0=Sun)
   │ │ │ └──── Month (1-12)
   │ │ └────── Day of month (1-31)
   │ └──────── Hour (0-23)
   └────────── Minute (0-59)
  ```

  ### Cách sử dụng:
  ```
  CronCreate({
    cron: "0 9 * * 1-5",      // Thứ 2-6 lúc 9:00 sáng
    prompt: "Kiểm tra PR mới và báo cáo",
    recurring: true
  })

  CronCreate({
    cron: "30 14 26 5 *",     // One-shot: hôm nay 14:30
    prompt: "Nhắc họp team",
    recurring: false
  })
  ```

  ### ⚠️ Lưu ý:
  - Jobs chỉ tồn tại trong session (trừ khi `durable: true`)
  - Tự động expire sau 7 ngày
  - **Tránh phút :00 và :30** (quá nhiều traffic) — dùng phút lẻ như :07, :23, :47
  - Chỉ chạy khi REPL đang idle

  ### Use cases:
  - Nhắc nhở định kỳ (daily standup, weekly review)
  - Tự động kiểm tra PR/deploy mỗi X phút
  - One-shot reminders

  ---

  ## 5. 🗑️ **CronDelete**
  **Mô tả:** Hủy một cron job đã tạo bằng `CronCreate`.

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `id` | string | ✅ | Job ID được trả về từ `CronCreate` |

  ### Cách sử dụng:
  ```
  CronDelete({ id: "job_abc123" })
  ```

  ### Use cases:
  - Hủy reminder sau khi đã xong việc
  - Dọn dẹp cron jobs không cần thiết

  ---

  ## 6. 📋 **CronList**
  **Mô tả:** Liệt kê tất cả cron jobs đang active trong session.

  ### Arguments: Không có

  ### Cách sử dụng:
  ```
  CronList()
  ```

  ### Use cases:
  - Kiểm tra những job nào đang chạy
  - Debug khi cron không kích hoạt như mong đợi
  - Lấy ID để xóa job

  ---

  ## 7. ✏️ **Edit**
  **Mô tả:** Thực hiện thay thế string chính xác trong file (tốt hơn Write cho việc sửa file).

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `file_path` | string | ✅ | Đường dẫn tuyệt đối đến file |
  | `old_string` | string | ✅ | Đoạn text cần thay thế (phải unique trong file) |
  | `new_string` | string | ✅ | Đoạn text mới thay vào |
  | `replace_all` | boolean | ❌ | `true` = thay thế tất cả occurrences |

  ### Cách sử dụng:
  ```
  Edit({
    file_path: "/project/src/app.ts",
    old_string: "const PORT = 3000;",
    new_string: "const PORT = process.env.PORT || 3000;"
  })

  // Rename variable toàn file
  Edit({
    file_path: "/project/src/utils.ts",
    old_string: "oldVariableName",
    new_string: "newVariableName",
    replace_all: true
  })
  ```

  ### ⚠️ Lưu ý quan trọng:
  - **Phải đọc file trước** bằng `Read` ít nhất 1 lần trong conversation
  - `old_string` phải **unique** trong file — nếu không, cung cấp thêm context xung quanh
  - Giữ nguyên indentation (tab/spaces) chính xác
  - Không dùng emoji trừ khi user yêu cầu

  ### Use cases:
  - Sửa bug cụ thể
  - Cập nhật config values
  - Refactor/rename variable, function
  - Thêm import statement

  ---

  ## 8. 🗺️ **EnterPlanMode**
  **Mô tả:** Chuyển Claude vào "Plan Mode" — khám phá codebase và lên kế hoạch trước khi implement.

  ### Arguments: Không có

  ### Cách sử dụng:
  ```
  EnterPlanMode()
  // Sau đó: explore codebase, thiết kế approach
  // Dùng AskUserQuestion nếu cần clarify
  // Kết thúc bằng ExitPlanMode()
  ```

  ### Workflow trong Plan Mode:
  1. Dùng Glob, Grep, Read để hiểu codebase
  2. Dùng AskUserQuestion nếu có điểm chưa rõ
  3. Viết plan vào plan file
  4. Gọi `ExitPlanMode` để user review và approve

  ### Khi nào dùng:
  - ✅ Feature mới phức tạp
  - ✅ Nhiều file bị ảnh hưởng (> 2-3 files)
  - ✅ Có nhiều hướng implementation
  - ✅ Cần quyết định kiến trúc
  - ❌ Sửa typo, bug đơn giản
  - ❌ Thêm 1 function rõ ràng

  ### Use cases:
  - Thiết kế authentication system
  - Refactor module lớn
  - Thêm feature ảnh hưởng nhiều component

  ---

  ## 9. 🌿 **EnterWorktree**
  **Mô tả:** Tạo và chuyển vào git worktree riêng biệt để làm việc isolated.

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `name` | string | ❌ | Tên cho worktree mới (mutually exclusive với `path`) |
  | `path` | string | ❌ | Đường dẫn đến worktree đã tồn tại |

  ### Cách sử dụng:
  ```
  // Tạo worktree mới
  EnterWorktree({ name: "feature-auth" })

  // Vào worktree đã có
  EnterWorktree({ path: ".claude/worktrees/feature-auth" })
  ```

  ### ⚠️ Lưu ý:
  - **Chỉ dùng khi user nói rõ "worktree"** hoặc CLAUDE.md yêu cầu
  - Không dùng để tạo branch thông thường — dùng git commands
  - Worktree được tạo trong `.claude/worktrees/`
  - Dùng `ExitWorktree` để thoát

  ### Use cases:
  - Làm việc trên feature branch mà không ảnh hưởng main
  - Test thay đổi trong môi trường isolated
  - Khi CLAUDE.md yêu cầu worktree workflow

  ---

  ## 10. ✅ **ExitPlanMode**
  **Mô tả:** Kết thúc Plan Mode và trình bày plan cho user approve.

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `allowedPrompts` | array | ❌ | Permissions cần thiết để implement plan |
  | `allowedPrompts[].tool` | string | ✅ | Tool cần permission (hiện chỉ `"Bash"`) |
  | `allowedPrompts[].prompt` | string | ✅ | Mô tả semantic action (e.g., "run tests") |

  ### Cách sử dụng:
  ```
  ExitPlanMode({
    allowedPrompts: [
      { tool: "Bash", prompt: "run tests" },
      { tool: "Bash", prompt: "install dependencies" }
    ]
  })
  ```

  ### ⚠️ Lưu ý:
  - **Không dùng AskUserQuestion** để hỏi "plan OK chưa?" — dùng tool này
  - Chỉ dùng khi đã viết xong plan vào plan file
  - Không dùng cho research/exploration tasks

  ---

  ## 11. 🚪 **ExitWorktree**
  **Mô tả:** Thoát khỏi worktree session và trở về working directory gốc.

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `action` | string | ✅ | `"keep"` = giữ lại worktree, `"remove"` = xóa |
  | `discard_changes` | boolean | ❌ | `true` = bắt buộc khi có uncommitted changes và muốn remove |

  ### Cách sử dụng:
  ```
  // Giữ lại work để dùng sau
  ExitWorktree({ action: "keep" })

  // Xóa worktree (công việc đã xong)
  ExitWorktree({ action: "remove" })

  // Xóa dù có uncommitted changes
  ExitWorktree({ action: "remove", discard_changes: true })
  ```

  ### Use cases:
  - Kết thúc feature development trong worktree
  - Clean up sau khi merge

  ---

  ## 12. 🔍 **Glob**
  **Mô tả:** Tìm kiếm file theo pattern glob, kết quả sort theo thời gian sửa đổi.

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `pattern` | string | ✅ | Glob pattern (e.g., `"**/*.ts"`, `"src/**/*.tsx"`) |
  | `path` | string | ❌ | Thư mục bắt đầu tìm (default: CWD) |

  ### Cách sử dụng:
  ```
  Glob({ pattern: "**/*.test.ts" })
  Glob({ pattern: "src/**/*.tsx", path: "/project" })
  Glob({ pattern: "**/*.{json,yaml}" })
  Glob({ pattern: "**/__tests__/**" })
  ```

  ### Use cases:
  - Tìm tất cả test files
  - Liệt kê components React
  - Tìm config files
  - Khám phá cấu trúc project

  ---

  ## 13. 🔎 **Grep**
  **Mô tả:** Tìm kiếm nội dung trong files bằng regex (dùng ripgrep).

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `pattern` | string | ✅ | Regex pattern cần tìm |
  | `path` | string | ❌ | File/thư mục tìm kiếm (default: CWD) |
  | `glob` | string | ❌ | Filter files (`"*.ts"`, `"**/*.tsx"`) |
  | `type` | string | ❌ | Loại file (`js`, `py`, `rust`, `go`...) |
  | `output_mode` | string | ❌ | `"files_with_matches"` (default), `"content"`, `"count"` |
  | `-i` | boolean | ❌ | Case insensitive |
  | `-n` | boolean | ❌ | Hiện số dòng |
  | `-C` / `context` | number | ❌ | Số dòng context xung quanh match |
  | `-A` | number | ❌ | Số dòng sau match |
  | `-B` | number | ❌ | Số dòng trước match |
  | `-o` | boolean | ❌ | Chỉ in phần match |
  | `multiline` | boolean | ❌ | Match across nhiều dòng |
  | `head_limit` | number | ❌ | Giới hạn số kết quả (default: 250) |
  | `offset` | number | ❌ | Skip N kết quả đầu |

  ### Cách sử dụng:
  ```
  // Tìm files có chứa "useState"
  Grep({ pattern: "useState", type: "ts", output_mode: "files_with_matches" })

  // Xem nội dung với context
  Grep({ 
    pattern: "function authenticate",
    output_mode: "content",
    context: 5
  })

  // Tìm định nghĩa class
  Grep({ 
    pattern: "class\\s+UserService",
    output_mode: "content",
    multiline: true
  })
  ```

  ### Use cases:
  - Tìm định nghĩa function/class/variable
  - Tìm tất cả nơi import một module
  - Tìm TODO/FIXME comments
  - Debug: tìm error message trong code

  ---

  ## 14. 👀 **Monitor**
  **Mô tả:** Chạy script nền và stream từng dòng stdout như events/notifications.

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `command` | string | ✅ | Shell script/command để chạy |
  | `description` | string | ✅ | Mô tả ngắn (hiển thị trong mỗi notification) |
  | `timeout_ms` | number | ✅ | Timeout tính ms (max 3600000ms) |
  | `persistent` | boolean | ✅ | `true` = chạy suốt session, `false` = có timeout |

  ### Cách sử dụng:
  ```
  // Monitor log file cho errors
  Monitor({
    command: "tail -f /var/log/app.log | grep -E --line-buffered 'ERROR|FATAL|Exception'",
    description: "Theo dõi errors trong app.log",
    timeout_ms: 300000,
    persistent: false
  })

  // Theo dõi CI checks cho PR
  Monitor({
    command: `
      prev=""
      while true; do
        s=$(gh pr checks 123 --json name,bucket)
        cur=$(jq -r '.[] | select(.bucket!="pending") | "\\(.name): \\(.bucket)"' <<<\"$s\" | sort)
        comm -13 <(echo "$prev") <(echo "$cur")
        prev=$cur
        jq -e 'all(.bucket!="pending")' <<<\"$s\" >/dev/null && break
        sleep 30
      done
    `,
    description: "CI checks cho PR #123",
    timeout_ms: 600000,
    persistent: false
  })
  ```

  ### ⚠️ Lưu ý quan trọng:
  - Dùng `grep --line-buffered` trong pipes (tránh delay)
  - Phải cover cả **failure cases** (không chỉ success)
  - Không dùng `tail -f` + `grep -m 1` (sẽ hang)
  - Dùng `TaskStop` để dừng monitor persistent
  - Mỗi dòng stdout = 1 notification

  ### Use cases:
  - Theo dõi server logs real-time
  - Monitor CI/CD pipeline
  - Watch file changes
  - Đợi service ready

  ---

  ## 15. 📓 **NotebookEdit**
  **Mô tả:** Chỉnh sửa cell trong Jupyter Notebook (.ipynb).

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `notebook_path` | string | ✅ | Đường dẫn tuyệt đối đến file .ipynb |
  | `new_source` | string | ✅ | Nội dung mới cho cell |
  | `cell_id` | string | ❌ | ID của cell cần edit |
  | `cell_type` | string | ❌ | `"code"` hoặc `"markdown"` |
  | `edit_mode` | string | ❌ | `"replace"` (default), `"insert"`, `"delete"` |

  ### Cách sử dụng:
  ```
  // Thay thế cell
  NotebookEdit({
    notebook_path: "/project/analysis.ipynb",
    cell_id: "abc123",
    new_source: "import pandas as pd\nimport numpy as np"
  })

  // Thêm cell mới sau cell có ID "xyz"
  NotebookEdit({
    notebook_path: "/project/notebook.ipynb",
    cell_id: "xyz",
    edit_mode: "insert",
    cell_type: "code",
    new_source: "df.head()"
  })

  // Xóa cell
  NotebookEdit({
    notebook_path: "/project/notebook.ipynb",
    cell_id: "cell_to_delete",
    edit_mode: "delete",
    new_source: ""
  })
  ```

  ### Use cases:
  - Cập nhật code trong data analysis notebook
  - Thêm documentation cell
  - Fix bug trong notebook
  - Tự động hóa notebook editing

  ---

  ## 16. 🔔 **PushNotification**
  **Mô tả:** Gửi desktop notification (và push đến điện thoại nếu có Remote Control).

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `message` | string | ✅ | Nội dung thông báo (tối đa 200 ký tự, 1 dòng) |
  | `status` | string | ✅ | Phải là `"proactive"` |

  ### Cách sử dụng:
  ```
  PushNotification({
    message: "Build failed: 3 auth tests failing in src/auth.test.ts",
    status: "proactive"
  })

  PushNotification({
    message: "Deploy to staging complete — ready for review",
    status: "proactive"
  })
  ```

  ### ⚠️ Lưu ý:
  - Chỉ dùng khi user **có thể đã rời đi** và có thông tin quan trọng
  - **Không notify** cho: progress thông thường, tác vụ nhanh, câu trả lời tức thì
  - Lead với thông tin actionable ("build failed: X" > "task done")
  - Không dùng markdown trong message

  ### Use cases:
  - Long-running task hoàn thành (build, test suite dài)
  - Phát hiện lỗi nghiêm trọng cần quyết định
  - User yêu cầu thông báo khi xong

  ---

  ## 17. 📖 **Read**
  **Mô tả:** Đọc nội dung file từ filesystem (hỗ trợ text, image, PDF, Jupyter notebook).

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `file_path` | string | ✅ | Đường dẫn tuyệt đối đến file |
  | `limit` | number | ❌ | Số dòng tối đa cần đọc |
  | `offset` | number | ❌ | Bắt đầu đọc từ dòng thứ N |
  | `pages` | string | ❌ | Chỉ cho PDF: range trang (e.g., `"1-5"`, `"3"`) |

  ### Cách sử dụng:
  ```
  // Đọc toàn file
  Read({ file_path: "/project/src/app.ts" })

  // Đọc từ dòng 100 đến 150
  Read({ file_path: "/project/src/app.ts", offset: 100, limit: 50 })

  // Đọc PDF trang 1-5
  Read({ file_path: "/docs/spec.pdf", pages: "1-5" })

  // Xem ảnh screenshot
  Read({ file_path: "/tmp/screenshot.png" })
  ```

  ### Format output:
  - Kết quả trả về dạng `cat -n` (có số dòng)
  - Số dòng bắt đầu từ 1

  ### ⚠️ Lưu ý:
  - **Bắt buộc đọc trước khi Edit**
  - PDF > 10 trang phải dùng `pages` parameter
  - Không re-read file vừa edit để verify (Edit tự track)

  ### Use cases:
  - Đọc source code để hiểu logic
  - Xem config files
  - Đọc PDF documentation
  - Xem screenshot/ảnh
  - Inspect Jupyter notebooks

  ---

  ## 18. ⏲️ **ScheduleWakeup**
  **Mô tả:** Lên lịch để tự động re-invoke prompt sau N giây (dùng trong `/loop` dynamic mode).

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `delaySeconds` | number | ✅ | Số giây chờ (clamp 60–3600) |
  | `prompt` | string | ✅ | Prompt sẽ chạy khi thức dậy |
  | `reason` | string | ✅ | Giải thích ngắn tại sao chọn delay này |

  ### Cách sử dụng:
  ```
  ScheduleWakeup({
    delaySeconds: 270,     // ~4.5 phút (giữ cache ấm)
    prompt: "Kiểm tra CI build status cho PR #123",
    reason: "Polling CI run dự kiến xong trong 8 phút"
  })

  // Autonomous loop
  ScheduleWakeup({
    delaySeconds: 1200,    // 20 phút
    prompt: "<<autonomous-loop-dynamic>>",
    reason: "Idle check, không có gì cần poll gấp"
  })
  ```

  ### Chiến lược chọn delay:
  | Scenario | Delay khuyến nghị |
  |----------|------------------|
  | Poll CI/deploy (~8 phút) | 270s × 2 lần |
  | Idle/không có gì gấp | 1200–1800s |
  | Chờ service local | 60–120s |
  | **Tránh** | Đúng 300s (cache miss không đáng) |

  ### Use cases:
  - Tự pace trong `/loop` dynamic mode
  - Poll external CI/deploy không có webhook
  - Periodic background checks

  ---

  ## 19. 📤 **ShareOnboardingGuide**
  **Mô tả:** Upload ONBOARDING.md và tạo shareable link cho teammates.

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `mode` | string | ❌ | `"check"` (default), `"update"`, `"create"`, `"delete"` |
  | `short_code` | string | ❌ | Short code của guide cụ thể cần target |

  ### Modes:
  - **`check`**: Nếu có ONBOARDING.md local → upload lên guide mới nhất (hoặc tạo mới); nếu không có → trả về link hiện tại
  - **`update`**: Upload vào guide cụ thể theo `short_code`
  - **`create`**: Luôn tạo link mới
  - **`delete`**: Xóa guide

  ### Cách sử dụng:
  ```
  // Upload và lấy link
  ShareOnboardingGuide({ mode: "check" })

  // Cập nhật guide cụ thể
  ShareOnboardingGuide({ mode: "update", short_code: "abc123" })

  // Tạo link hoàn toàn mới
  ShareOnboardingGuide({ mode: "create" })
  ```

  ### Use cases:
  - Chia sẻ onboarding guide với team member mới
  - Cập nhật documentation cho project

  ---

  ## 20. 🔧 **Skill**
  **Mô tả:** Thực thi một "skill" (slash command chuyên biệt) trong conversation chính.

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `skill` | string | ✅ | Tên skill (không có `/`) |
  | `args` | string | ❌ | Arguments truyền vào skill |

  ### Skills có sẵn:
  | Skill | Mô tả |
  |-------|-------|
  | `update-config` | Cấu hình settings.json, hooks, permissions |
  | `keybindings-help` | Tùy chỉnh keyboard shortcuts |
  | `verify` | Verify code change hoạt động đúng |
  | `code-review` | Review diff tìm bugs |
  | `fewer-permission-prompts` | Giảm permission prompts |
  | `loop` | Chạy prompt lặp lại theo interval |
  | `claude-api` | Build/debug Anthropic SDK apps |
  | `run` | Launch và chạy app |
  | `init` | Tạo CLAUDE.md |
  | `review` | Review pull request |
  | `security-review` | Security audit |

  ### Cách sử dụng:
  ```
  Skill({ skill: "code-review", args: "--comment" })
  Skill({ skill: "init" })
  Skill({ skill: "run" })
  Skill({ skill: "update-config" })
  ```

  ### ⚠️ Lưu ý:
  - **Bắt buộc** gọi skill TRƯỚC khi generate response khác
  - Chỉ gọi skill có trong danh sách available
  - Không gọi skill đang running
  - Không dùng cho built-in commands (`/help`, `/clear`)

  ---

  ## 21. 📝 **TaskCreate**
  **Mô tả:** Tạo task mới trong task list để track tiến độ.

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `subject` | string | ✅ | Tiêu đề ngắn dạng imperative (e.g., "Fix auth bug") |
  | `description` | string | ✅ | Chi tiết công việc cần làm |
  | `activeForm` | string | ❌ | Dạng present continuous khi đang làm (e.g., "Fixing auth bug") |
  | `metadata` | object | ❌ | Metadata tùy ý |

  ### Cách sử dụng:
  ```
  TaskCreate({
    subject: "Add user authentication",
    description: "Implement JWT-based auth with login/logout endpoints",
    activeForm: "Adding user authentication"
  })
  ```

  ### Khi nào dùng:
  - ✅ Tác vụ phức tạp >= 3 bước
  - ✅ User cung cấp danh sách việc cần làm
  - ✅ Plan mode tasks
  - ❌ Tác vụ đơn giản 1-2 bước

  ### Use cases:
  - Track multi-step feature implementation
  - Manage backlog khi user đưa nhiều yêu cầu
  - Hiển thị progress cho user

  ---

  ## 22. 🔍 **TaskGet**
  **Mô tả:** Lấy thông tin đầy đủ của một task theo ID.

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `taskId` | string | ✅ | ID của task |

  ### Cách sử dụng:
  ```
  TaskGet({ taskId: "42" })
  ```

  ### Output trả về:
  - `subject`, `description`, `status`
  - `blocks`: Tasks đang chờ task này xong
  - `blockedBy`: Tasks phải xong trước task này

  ### Use cases:
  - Đọc đầy đủ requirements trước khi bắt đầu
  - Kiểm tra dependencies của task

  ---

  ## 23. 📋 **TaskList**
  **Mô tả:** Liệt kê tất cả tasks với summary.

  ### Arguments: Không có

  ### Cách sử dụng:
  ```
  TaskList()
  ```

  ### Output:
  - `id`, `subject`, `status` (`pending`/`in_progress`/`completed`)
  - `owner`: Agent ID nếu đã assign
  - `blockedBy`: Task IDs đang block

  ### Use cases:
  - Kiểm tra tổng quan tiến độ
  - Tìm task tiếp theo cần làm
  - Phát hiện tasks bị blocked

  ---

  ## 24. 📤 **TaskOutput**
  **Mô tả:** Lấy output từ background task đang chạy hoặc đã hoàn thành.

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `task_id` | string | ✅ | ID của task |
  | `block` | boolean | ✅ | `true` = chờ xong (default), `false` = check ngay |
  | `timeout` | number | ✅ | Thời gian chờ tối đa (ms, max 600000) |

  ### ⚠️ Deprecated:
  Tool này đã **deprecated**. Thay thế:
  - Background bash tasks → dùng **Read** trên output file path
  - Local agent tasks → dùng **Agent** tool result trực tiếp
  - Remote agent tasks → dùng **Read** trên output file path

  ---

  ## 25. 🛑 **TaskStop**
  **Mô tả:** Dừng một background task đang chạy.

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `task_id` | string | ✅ | ID của task cần dừng |

  ### Cách sử dụng:
  ```
  TaskStop({ task_id: "task_abc123" })
  ```

  ### Use cases:
  - Dừng Monitor persistent khi không cần nữa
  - Cancel long-running background process
  - Kill hung process

  ---

  ## 26. 🔄 **TaskUpdate**
  **Mô tả:** Cập nhật trạng thái, thông tin, hoặc dependencies của task.

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `taskId` | string | ✅ | ID của task |
  | `status` | string | ❌ | `"pending"`, `"in_progress"`, `"completed"`, `"deleted"` |
  | `subject` | string | ❌ | Tiêu đề mới |
  | `description` | string | ❌ | Mô tả mới |
  | `activeForm` | string | ❌ | Present continuous form |
  | `owner` | string | ❌ | Assign cho agent |
  | `metadata` | object | ❌ | Merge metadata keys |
  | `addBlocks` | array | ❌ | Task IDs mà task này blocks |
  | `addBlockedBy` | array | ❌ | Task IDs phải xong trước task này |

  ### Cách sử dụng:
  ```
  // Bắt đầu làm task
  TaskUpdate({ taskId: "1", status: "in_progress" })

  // Hoàn thành task
  TaskUpdate({ taskId: "1", status: "completed" })

  // Set dependency
  TaskUpdate({ taskId: "3", addBlockedBy: ["1", "2"] })

  // Xóa task
  TaskUpdate({ taskId: "5", status: "deleted" })
  ```

  ### ⚠️ Lưu ý:
  - Đọc task state mới nhất bằng `TaskGet` trước khi update
  - **Chỉ mark completed khi THỰC SỰ xong** — không mark nếu còn lỗi

  ### Status Workflow:
  ```
  pending → in_progress → completed
                ↓
             deleted
  ```

  ---

  ## 27. 🌐 **WebFetch**
  **Mô tả:** Fetch URL và dùng AI model để xử lý/extract thông tin từ content.

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `url` | string | ✅ | URL đầy đủ (tự động upgrade HTTP → HTTPS) |
  | `prompt` | string | ✅ | Câu hỏi/yêu cầu về nội dung trang |

  ### Cách sử dụng:
  ```
  WebFetch({
    url: "https://docs.react.dev/reference/react/useState",
    prompt: "Giải thích useState hook và ví dụ sử dụng"
  })

  WebFetch({
    url: "https://api.github.com/repos/owner/repo",
    prompt: "Lấy thông tin stars, forks, và description"
  })
  ```

  ### ⚠️ Lưu ý:
  - **KHÔNG hoạt động** với URL authenticated/private (Google Docs, Confluence, Jira)
  - Có cache 15 phút
  - Dùng `gh` CLI thay vì WebFetch cho GitHub URLs
  - Kết quả có thể bị summarize nếu content quá lớn

  ### Use cases:
  - Đọc documentation
  - Fetch API data công khai
  - Lấy thông tin từ trang web
  - Đọc changelogs, release notes

  ---

  ## 28. 🔍 **WebSearch**
  **Mô tả:** Tìm kiếm thông tin trên internet và trả về kết quả.

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `query` | string | ✅ | Search query (tối thiểu 2 ký tự) |
  | `allowed_domains` | array | ❌ | Chỉ lấy kết quả từ các domain này |
  | `blocked_domains` | array | ❌ | Loại bỏ kết quả từ các domain này |

  ### Cách sử dụng:
  ```
  WebSearch({ query: "React 19 new features 2026" })

  WebSearch({
    query: "Next.js 15 App Router documentation",
    allowed_domains: ["nextjs.org", "vercel.com"]
  })

  WebSearch({
    query: "Python asyncio best practices",
    blocked_domains: ["w3schools.com"]
  })
  ```

  ### ⚠️ Lưu ý:
  - Chỉ hoạt động ở **US**
  - **Bắt buộc** thêm mục "Sources:" với links vào response
  - Dùng năm hiện tại (2026) khi search thông tin mới nhất

  ### Use cases:
  - Thông tin về events/releases sau knowledge cutoff
  - Tìm documentation mới nhất
  - Research công nghệ, libraries
  - Kiểm tra current best practices

  ---

  ## 29. 📝 **Write**
  **Mô tả:** Ghi nội dung vào file (tạo mới hoặc overwrite hoàn toàn).

  ### Arguments:
  | Tham số | Kiểu | Bắt buộc | Mô tả |
  |---------|------|----------|-------|
  | `file_path` | string | ✅ | Đường dẫn tuyệt đối đến file |
  | `content` | string | ✅ | Nội dung cần ghi |

  ### Cách sử dụng:
  ```
  Write({
    file_path: "/project/src/utils/helpers.ts",
    content: `export function formatDate(date: Date): string {
    return date.toISOString().split('T')[0];
  }`
  })
  ```

  ### ⚠️ Lưu ý quan trọng:
  - **Đây là OVERWRITE hoàn toàn** — dùng `Edit` nếu chỉ sửa một phần
  - Nếu file đã tồn tại, **phải Read trước**
  - **Ưu tiên Edit** cho file có sẵn
  - Không tạo file `.md`/README trừ khi được yêu cầu rõ ràng
  - Không dùng emoji trừ khi user yêu cầu

  ### Use cases:
  - Tạo file mới từ đầu
  - Viết lại hoàn toàn file nhỏ
  - Tạo config files
  - Tạo test files mới

  ---

  ## 📊 Bảng tóm tắt nhanh

  | Tool | Nhóm | Mục đích chính |
  |------|------|---------------|
  | `Agent` | Orchestration | Spawn sub-agent cho tasks phức tạp |
  | `AskUserQuestion` | Interaction | Hỏi user để clarify |
  | `Bash` | System | Chạy lệnh shell |
  | `CronCreate/Delete/List` | Scheduling | Lên lịch tác vụ |
  | `Edit` | File | Sửa một phần file |
  | `Write` | File | Tạo/ghi lại toàn bộ file |
  | `Read` | File | Đọc nội dung file |
  | `Glob` | Search | Tìm file theo pattern |
  | `Grep` | Search | Tìm nội dung trong files |
  | `EnterPlanMode/ExitPlanMode` | Planning | Lập kế hoạch trước implement |
  | `EnterWorktree/ExitWorktree` | Git | Làm việc trong isolated worktree |
  | `Monitor` | Async | Stream events từ process |
  | `ScheduleWakeup` | Scheduling | Self-pace trong loop mode |
  | `NotebookEdit` | File | Sửa Jupyter notebook |
  | `PushNotification` | Notification | Thông báo đến user |
  | `ShareOnboardingGuide` | Sharing | Chia sẻ onboarding guide |
  | `Skill` | Orchestration | Gọi slash command/skill |
  | `TaskCreate/Get/List/Update` | Task | Quản lý task list |
  | `TaskOutput/Stop` | Task | Control background tasks |
  | `WebFetch` | Web | Đọc nội dung URL |
  | `WebSearch` | Web | Tìm kiếm internet |