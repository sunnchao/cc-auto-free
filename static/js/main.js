/**
 * Cursor Accounts 管理系统前端脚本
 */

$(document).ready(function() {
    // 初始加载数据
    loadAccounts();
    
    // 搜索按钮点击事件
    $('#searchButton').click(function() {
        const searchTerm = $('#searchInput').val().trim();
        searchAccounts(searchTerm);
    });
    
    // 搜索框回车事件
    $('#searchInput').keypress(function(event) {
        if (event.which === 13) {
            const searchTerm = $(this).val().trim();
            searchAccounts(searchTerm);
        }
    });
    
    // 刷新按钮点击事件
    $('#refreshButton').click(function() {
        $(this).find('i').addClass('fa-spin');
        loadAccounts().then(() => {
            setTimeout(() => {
                $(this).find('i').removeClass('fa-spin');
            }, 500);
        });
    });
    
    // 复制API URL按钮点击事件
    $('.copy-btn').click(function() {
        const url = window.location.origin + $(this).data('url');
        copyToClipboard(url);
        
        // 显示复制成功提示
        const originalHtml = $(this).html();
        $(this).html('<i class="fas fa-check"></i> 已复制');
        
        setTimeout(() => {
            $(this).html(originalHtml);
        }, 1500);
    });
    
    // 绑定表格内的复制按钮事件（动态添加的元素）
    $(document).on('click', '.copy-token-btn, .copy-email-btn, .copy-password-btn', function() {
        const content = $(this).data('content');
        copyToClipboard(content);
        
        // 显示复制成功提示
        const $this = $(this);
        const originalClass = $this.find('i').attr('class');
        $this.find('i').attr('class', 'fas fa-check');
        
        setTimeout(() => {
            $this.find('i').attr('class', originalClass);
        }, 1000);
    });
    
    // 复制Token结果按钮
    $(document).on('click', '.copy-token-result-btn', function() {
        const content = $('#tokenResultText').text();
        if (content) {
            copyToClipboard(content);
            
            // 显示复制成功提示
            const $this = $(this);
            const originalHtml = $this.html();
            $this.html('<i class="fas fa-check"></i> 已复制');
            
            setTimeout(() => {
                $this.html(originalHtml);
            }, 1500);
        }
    });
    
    // 绑定详情切换按钮事件
    $(document).on('click', '.details-toggle', function() {
        const accountId = $(this).data('id');
        const detailsSection = $('#details-' + accountId);
        
        if (detailsSection.is(':visible')) {
            detailsSection.slideUp();
            $(this).find('i').removeClass('fa-chevron-up').addClass('fa-chevron-down');
        } else {
            detailsSection.slideDown();
            $(this).find('i').removeClass('fa-chevron-down').addClass('fa-chevron-up');
        }
    });
    
    // 获取Token表单提交事件
    $('#getTokenForm').submit(function(event) {
        event.preventDefault();
        
        const email = $('#tokenEmail').val().trim();
        const password = $('#tokenPassword').val().trim();
        
        if (!email || !password) {
            showError('邮箱和密码不能为空');
            return;
        }
        
        // 禁用按钮并显示加载状态
        $('#getTokenButton').prop('disabled', true);
        $('#tokenSpinner').removeClass('d-none');
        $('#tokenButtonText').text('获取中...');
        $('#tokenResult').hide();
        
        // 发送请求获取Token
        $.ajax({
            url: '/api/get_cursor_token',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                email: email,
                password: password
            }),
            success: function(response) {
                if (response.status === 'success') {
                    // 显示Token结果
                    $('#tokenResultText').text(response.token);
                    $('#tokenResult').slideDown();
                    
                    // 存储邮箱和密码到按钮中，以便保存到数据库时使用
                    $('.save-token-btn').data('email', email);
                    $('.save-token-btn').data('password', password);
                    $('.save-token-btn').data('token', response.token);
                    
                    // 添加成功提示
                    showAlert('Token获取成功', 'success');
                } else {
                    showAlert('获取失败: ' + response.message, 'danger');
                }
            },
            error: function(xhr) {
                let errorMessage = '请求失败';
                try {
                    const response = JSON.parse(xhr.responseText);
                    errorMessage = response.message || errorMessage;
                } catch (e) {
                    errorMessage = `请求失败 (${xhr.status})`;
                }
                showAlert(errorMessage, 'danger');
            },
            complete: function() {
                // 恢复按钮状态
                $('#getTokenButton').prop('disabled', false);
                $('#tokenSpinner').addClass('d-none');
                $('#tokenButtonText').text('获取Token');
            }
        });
    });
    
    // 保存Token到数据库按钮点击事件
    $(document).on('click', '.save-token-btn', function() {
        const email = $(this).data('email');
        const password = $(this).data('password');
        const token = $(this).data('token');
        
        if (!email || !password || !token) {
            showAlert('保存失败：缺少必要的账号信息', 'danger');
            return;
        }
        
        // 禁用按钮并显示加载状态
        const $btn = $(this);
        const originalHtml = $btn.html();
        $btn.html('<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 保存中...');
        $btn.prop('disabled', true);
        
        // 发送请求保存Token
        $.ajax({
            url: '/api/save_token',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                email: email,
                password: password,
                token: token,
                usage_info: '未知' // 默认使用信息
            }),
            success: function(response) {
                if (response.status === 'success') {
                    showAlert('账号信息已成功保存到数据库', 'success');
                    // 刷新账号列表
                    loadAccounts();
                } else {
                    showAlert('保存失败: ' + response.message, 'danger');
                }
            },
            error: function(xhr) {
                let errorMessage = '请求失败';
                try {
                    const response = JSON.parse(xhr.responseText);
                    errorMessage = response.message || errorMessage;
                } catch (e) {
                    errorMessage = `请求失败 (${xhr.status})`;
                }
                showAlert(errorMessage, 'danger');
            },
            complete: function() {
                // 恢复按钮状态
                $btn.html(originalHtml);
                $btn.prop('disabled', false);
            }
        });
    });
});

/**
 * 显示提示信息
 */
function showAlert(message, type) {
    // 创建提示元素
    const alertId = 'alert-' + Date.now();
    const alertHtml = `
        <div id="${alertId}" class="alert alert-${type} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    `;
    
    // 添加到页面
    const alertContainer = $('<div class="mt-3"></div>');
    alertContainer.html(alertHtml);
    $('#getTokenForm').after(alertContainer);
    
    // 5秒后自动关闭
    setTimeout(() => {
        $(`#${alertId}`).alert('close');
    }, 5000);
}

/**
 * 加载所有账号数据
 */
function loadAccounts() {
    $('#loadingSpinner').show();
    $('#accountsTableContainer').hide();
    $('#emptyState').hide();
    
    return fetch('/api/accounts')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                renderAccountsTable(data.data);
                updateAccountCount(data.count);
            } else {
                showError('加载数据失败: ' + data.message);
            }
        })
        .catch(error => {
            showError('请求出错: ' + error);
        })
        .finally(() => {
            $('#loadingSpinner').hide();
        });
}

/**
 * 搜索账号
 */
function searchAccounts(query) {
    if (!query) {
        return loadAccounts();
    }
    
    $('#loadingSpinner').show();
    $('#accountsTableContainer').hide();
    $('#emptyState').hide();
    
    fetch(`/api/search?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                renderAccountsTable(data.data);
                updateAccountCount(data.count);
            } else {
                showError('搜索失败: ' + data.message);
            }
        })
        .catch(error => {
            showError('搜索请求出错: ' + error);
        })
        .finally(() => {
            $('#loadingSpinner').hide();
        });
}

/**
 * 渲染账号数据表格
 */
function renderAccountsTable(accounts) {
    const tableBody = $('#accountsTableBody');
    tableBody.empty();
    
    if (accounts.length === 0) {
        $('#accountsTableContainer').hide();
        $('#emptyState').show();
        return;
    }
    
    accounts.forEach(account => {
        const row = `
            <tr>
                <td>${account.id}</td>
                <td>
                    ${account.email}
                    <button class="btn btn-sm text-primary copy-email-btn" data-content="${account.email}" title="复制邮箱">
                        <i class="fas fa-copy"></i>
                    </button>
                </td>
                <td>
                    ${account.password}
                    <button class="btn btn-sm text-primary copy-password-btn" data-content="${account.password}" title="复制密码">
                        <i class="fas fa-copy"></i>
                    </button>
                </td>
                <td class="token-cell">
                    ${formatToken(account.token)}
                    <button class="btn btn-sm text-primary copy-token-btn" data-content="${account.token || ''}" title="复制Token">
                        <i class="fas fa-copy"></i>
                    </button>
                </td>
                <td><span class="usage-badge">${account.usage_info || '未知'}</span></td>
                <td>${formatDate(account.created_at)}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary details-toggle" data-id="${account.id}">
                        详情 <i class="fas fa-chevron-down"></i>
                    </button>
                </td>
            </tr>
            <tr>
                <td colspan="7" style="padding: 0;">
                    <div id="details-${account.id}" class="account-details">
                        <div class="row">
                            <div class="col-md-6">
                                <h6>完整账号信息</h6>
                                <div class="mb-2">
                                    <strong>ID:</strong> ${account.id}
                                </div>
                                <div class="mb-2">
                                    <strong>邮箱:</strong> ${account.email}
                                </div>
                                <div class="mb-2">
                                    <strong>密码:</strong> ${account.password}
                                </div>
                                <div class="mb-2">
                                    <strong>创建时间:</strong> ${formatDate(account.created_at)}
                                </div>
                            </div>
                            <div class="col-md-6">
                                <h6>Token (完整)</h6>
                                <div class="p-2 bg-light rounded">
                                    <code style="word-break: break-all;">${account.token || '未设置'}</code>
                                </div>
                                <div class="mt-2">
                                    <button class="btn btn-sm btn-outline-secondary copy-token-btn" data-content="${account.token || ''}" title="复制Token">
                                        <i class="fas fa-copy"></i> 复制Token
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </td>
            </tr>
        `;
        tableBody.append(row);
    });
    
    $('#accountsTableContainer').show();
}

/**
 * 格式化Token显示
 */
function formatToken(token) {
    if (!token) return '未设置';
    return token.length > 20 ? token.substring(0, 20) + '...' : token;
}

/**
 * 格式化日期显示
 */
function formatDate(dateString) {
    if (!dateString) return '未知';
    
    try {
        const date = new Date(dateString);
        return date.toLocaleString('zh-CN', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (e) {
        return dateString;
    }
}

/**
 * 更新账号数量显示
 */
function updateAccountCount(count) {
    $('#accountCount').text(`共 ${count} 个账号`);
}

/**
 * 显示错误信息
 */
function showError(message) {
    console.error(message);
    showAlert(message, 'danger');
}

/**
 * 复制内容到剪贴板
 */
function copyToClipboard(text) {
    // 使用现代剪贴板API
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text)
            .catch(err => {
                console.error('复制失败:', err);
                // 回退到传统方法
                fallbackCopyToClipboard(text);
            });
    } else {
        // 回退到传统复制方法
        fallbackCopyToClipboard(text);
    }
}

/**
 * 传统复制到剪贴板方法（回退方案）
 */
function fallbackCopyToClipboard(text) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-999999px';
    textArea.style.top = '-999999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    
    try {
        document.execCommand('copy');
    } catch (err) {
        console.error('Fallback: 复制失败', err);
    }
    
    document.body.removeChild(textArea);
} 