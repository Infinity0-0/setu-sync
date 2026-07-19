document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.multiple = true;
    fileInput.style.display = 'none';
    document.body.appendChild(fileInput);
    
    const folderInput = document.createElement('input');
    folderInput.type = 'file';
    folderInput.multiple = true;
    folderInput.webkitdirectory = true;
    folderInput.style.display = 'none';
    document.body.appendChild(folderInput);
    
    const dropZone = document.getElementById('dropZone');
    const dropZoneText = document.getElementById('dropZoneText');
    const dropZoneSubtext = document.getElementById('dropZoneSubtext');
    const fileModeBtn = document.getElementById('fileModeBtn');
    const folderModeBtn = document.getElementById('folderModeBtn');
    const selectedFilesContainer = document.getElementById('selectedFiles');
    const getQrBtn = document.getElementById('getQrBtn');
    const uploadResult = document.getElementById('uploadResult');
    const passwordInput = document.getElementById('filePassword');
    const oneTimeDownloadCheckbox = document.getElementById('oneTimeDownload');
    const downloadBtn = document.getElementById('downloadBtn');
    const quickDownloadBtn = document.getElementById('quickDownloadBtn');
    const receiveCodeInput = document.getElementById('receiveCode');
    const quickReceiveCode = document.getElementById('quickReceiveCode');
    const downloadArea = document.getElementById('downloadArea');
    const downloadFilesList = document.getElementById('downloadFilesList');
    const passwordArea = document.getElementById('passwordArea');
    const downloadPassword = document.getElementById('downloadPassword');
    const downloadFilesBtn = document.getElementById('downloadFilesBtn');
    const expireNowBtn = document.getElementById('expireNowBtn');
    const historyList = document.getElementById('historyList');
    
    let files = [];
    let uploadHistory = [];
    let currentShareId = null;
    let currentDeleteToken = null;
    let timerInterval = null;
    let expiryTime = null;
    let uploadMode = 'files';
    let folderRelativePaths = [];
    let folderName = '';
    
    // Auto-detect: use local API when served from localhost, otherwise Render
    const API_BASE = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
      ? `http://${window.location.hostname}:8000`
      : 'https://setu-backend-txdk.onrender.com';
    
    fileModeBtn.addEventListener('click', function(e) {
        e.preventDefault();
        fileModeBtn.classList.add('active');
        folderModeBtn.classList.remove('active');
        uploadMode = 'files';
        dropZoneText.textContent = 'Drop files here or click';
        dropZoneSubtext.textContent = 'Max: 10GB per Upload';
        folderRelativePaths = [];
        folderName = '';
    });
    
    folderModeBtn.addEventListener('click', function(e) {
        e.preventDefault();
        folderModeBtn.classList.add('active');
        fileModeBtn.classList.remove('active');
        uploadMode = 'folder';
        dropZoneText.textContent = 'Drop a folder here or click';
        dropZoneSubtext.textContent = 'Folder will be zipped & uploaded';
        files = [];
        folderRelativePaths = [];
        folderName = '';
        renderFileList();
        resetDropZone();
    });
    
    dropZone.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        if (uploadMode === 'folder') folderInput.click();
        else fileInput.click();
    });
    
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(function(ev) {
        dropZone.addEventListener(ev, function(e) { e.preventDefault(); e.stopPropagation(); }, false);
    });
    
    dropZone.addEventListener('dragenter', function() { dropZone.style.borderColor = '#10b981'; dropZone.style.background = 'rgba(16,185,129,0.12)'; });
    dropZone.addEventListener('dragover', function() { dropZone.style.borderColor = '#10b981'; dropZone.style.background = 'rgba(16,185,129,0.12)'; });
    dropZone.addEventListener('dragleave', function() { dropZone.style.borderColor = '#3b82f6'; dropZone.style.background = 'rgba(59,130,246,0.04)'; });
    
    dropZone.addEventListener('drop', function(e) {
        dropZone.style.borderColor = '#3b82f6';
        dropZone.style.background = 'rgba(59,130,246,0.04)';
        var items = e.dataTransfer.items;
        if (items && items.length > 0) {
            var hasDir = false;
            for (var i = 0; i < items.length; i++) {
                if (items[i].webkitGetAsEntry && items[i].webkitGetAsEntry().isDirectory) { hasDir = true; break; }
            }
            if (hasDir) {
                uploadMode = 'folder';
                fileModeBtn.classList.remove('active');
                folderModeBtn.classList.add('active');
                dropZoneText.textContent = 'Drop a folder here or click';
                dropZoneSubtext.textContent = 'Folder will be zipped & uploaded';
                handleDroppedFolder(items);
            } else {
                var df = e.dataTransfer.files;
                if (df.length > 0) handleFiles(df);
            }
        } else {
            var df = e.dataTransfer.files;
            if (df.length > 0) handleFiles(df);
        }
    });
    
    fileInput.addEventListener('change', function() { if (fileInput.files.length > 0) handleFiles(fileInput.files); });
    folderInput.addEventListener('change', function() { if (folderInput.files.length > 0) handleFolderFiles(folderInput.files); });
    
    function handleDroppedFolder(items) {
        var entries = [];
        for (var i = 0; i < items.length; i++) {
            var entry = items[i].webkitGetAsEntry();
            if (entry) entries.push(entry);
        }
        if (entries.length === 0) return;
        var first = entries[0];
        if (first.isDirectory) {
            folderName = first.name;
            traverseFolder(first, folderName, function(allFiles, allPaths) {
                if (allFiles.length > 0) {
                    files = allFiles; folderRelativePaths = allPaths;
                    renderFileList();
                    dropZone.innerHTML = '<i class="fas fa-folder-open display-4 mb-2" style="color:#10b981"></i><h6>Folder: ' + folderName + '</h6><p class="small text-muted mb-0">' + files.length + ' file(s)</p>';
                    if (files.length > 500) {
                        alert('Large folder (' + files.length + ' files). Upload may take time depending on your internet speed.');
                    }
                }
            });
        }
    }
    
    function traverseFolder(entry, basePath, callback) {
        var allFiles = []; var allPaths = [];
        function readEntries(dirEntry, curPath) {
            return new Promise(function(resolve, reject) {
                var reader = dirEntry.createReader(); var entries = [];
                function readBatch() {
                    reader.readEntries(function(results) {
                        if (results.length === 0) resolve(entries);
                        else { entries.push.apply(entries, results); readBatch(); }
                    }, reject);
                }
                readBatch();
            }).then(function(entries) {
                var proms = entries.map(function(e) {
                    if (e.isDirectory) return readEntries(e, curPath + '/' + e.name);
                    else {
                        var fp = curPath + '/' + e.name;
                        return new Promise(function(resolve, reject) {
                            e.file(function(f) {
                                try { Object.defineProperty(f, 'webkitRelativePath', { value: fp }); } catch(ex) {}
                                allFiles.push(f); allPaths.push(fp); resolve();
                            }, reject);
                        });
                    }
                });
                return Promise.all(proms);
            });
        }
        readEntries(entry, basePath).then(function() { callback(allFiles, allPaths); })
        .catch(function(err) { console.error('Folder error:', err); alert('Error reading folder: ' + err.message); });
    }
    
    function handleFolderFiles(fileList) {
        var newFiles = Array.from(fileList);
        if (newFiles.length === 0) return;
        var firstPath = newFiles[0].webkitRelativePath || newFiles[0].name;
        folderName = firstPath.split('/')[0];
        folderRelativePaths = newFiles.map(function(f) { return f.webkitRelativePath || f.name; });
        files = newFiles;
        renderFileList();
        dropZone.innerHTML = '<i class="fas fa-folder-open display-4 mb-2" style="color:#10b981"></i><h6>Folder: ' + folderName + '</h6><p class="small text-muted mb-0">' + files.length + ' file(s)</p>';
        dropZone.classList.add('pulse');
        setTimeout(function() { dropZone.classList.remove('pulse'); }, 2000);
        if (files.length > 500) {
            setTimeout(function() { alert('Large folder (' + files.length + ' files). Upload may take time.'); }, 500);
        }
    }
    
    function handleFiles(fileList) {
        var newFiles = Array.from(fileList);
        for (var i = 0; i < newFiles.length; i++) {
            if (newFiles[i].size > 10 * 1024 * 1024 * 1024) { alert('File "' + newFiles[i].name + '" exceeds 10GB limit!'); return; }
        }
        files = files.concat(newFiles);
        folderRelativePaths = [];
        renderFileList();
        dropZone.innerHTML = '<i class="fas fa-check-circle display-4 mb-2" style="color:#10b981"></i><h6>' + files.length + ' file(s) selected</h6><p class="small text-muted mb-0">Click "Generate QR Code" to share</p>';
        dropZone.classList.add('pulse');
        setTimeout(function() { dropZone.classList.remove('pulse'); }, 2000);
    }
    
    function renderFileList() {
        selectedFilesContainer.innerHTML = '';
        if (files.length === 0) {
            selectedFilesContainer.innerHTML = '<p class="text-muted text-center py-3 small">No files selected. Use the upload area on the left side.</p>';
            return;
        }
        var html = '';
        if (uploadMode === 'folder' && folderName) {
            html += '<div class="file-item" style="background:rgba(16,185,129,0.08);border-color:rgba(16,185,129,0.25);">';
            html += '<div class="d-flex align-items-center">';
            html += '<i class="fas fa-folder-open me-2" style="font-size:20px;color:#10b981;"></i>';
            html += '<div><div style="font-weight:700;color:#059669;font-size:0.9rem;">📁 ' + folderName + '/</div>';
            html += '<div class="small text-muted">' + files.length + ' file(s) inside</div></div></div></div>';
        }
        var displayCount = Math.min(files.length, 50);
        for (var i = 0; i < displayCount; i++) {
            var file = files[i];
            var relPath = folderRelativePaths[i] || file.name;
            var dispName = (uploadMode === 'folder' && relPath) ? relPath.replace(/^[^\/]+\//, '') : file.name;
            if (dispName.length > 40) dispName = dispName.substring(0, 37) + '...';
            html += '<div class="file-item"><div class="d-flex justify-content-between align-items-center">';
            html += '<div class="d-flex align-items-center flex-grow-1" style="min-width:0;">';
            html += '<i class="fas fa-file me-2" style="font-size:16px;color:#3b82f6;flex-shrink:0;"></i>';
            html += '<div style="overflow:hidden;"><div style="font-weight:600;font-size:0.82rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + dispName + '</div>';
            html += '<div class="small text-muted" style="font-size:0.75rem;">' + formatFileSize(file.size) + '</div></div></div>';
            html += '<button class="btn btn-outline-danger btn-sm remove-file ms-2" data-idx="' + i + '" style="flex-shrink:0;"><i class="fas fa-times"></i></button></div></div>';
        }
        if (files.length > 50) {
            html += '<div class="text-center mt-2 text-muted small"><em>...and ' + (files.length - 50) + ' more files</em></div>';
        }
        selectedFilesContainer.innerHTML = html;
        var btns = selectedFilesContainer.querySelectorAll('.remove-file');
        for (var j = 0; j < btns.length; j++) {
            btns[j].addEventListener('click', function() {
                var idx = parseInt(this.getAttribute('data-idx'));
                files.splice(idx, 1);
                if (folderRelativePaths.length > idx) folderRelativePaths.splice(idx, 1);
                renderFileList();
                if (files.length === 0) resetDropZone();
                else if (uploadMode === 'folder')
                    dropZone.innerHTML = '<i class="fas fa-folder-open display-4 mb-2" style="color:#10b981"></i><h6>Folder: ' + folderName + '</h6><p class="small text-muted mb-0">' + files.length + ' file(s) selected</p>';
                else
                    dropZone.innerHTML = '<i class="fas fa-check-circle display-4 mb-2" style="color:#10b981"></i><h6>' + files.length + ' file(s) selected</h6><p class="small text-muted mb-0">Click "Generate QR Code" to share</p>';
            });
        }
    }
    
    function resetDropZone() {
        if (uploadMode === 'folder')
            dropZone.innerHTML = '<i class="fas fa-folder-open display-4 mb-2" style="color:#3b82f6;"></i><h6>Drop a folder here or click</h6><p class="small text-muted mb-0">Folder will be zipped & uploaded</p>';
        else
            dropZone.innerHTML = '<i class="fas fa-file-upload display-4 mb-2" style="color:#3b82f6;"></i><h6>Drop files here or click</h6><p class="small text-muted mb-0">Max: 10GB per Upload</p>';
    }
    
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        var k = 1024; var sizes = ['B','KB','MB','GB','TB'];
        var i = Math.floor(Math.log(bytes) / Math.log(k));
        return (bytes / Math.pow(k, i)).toFixed(1) + ' ' + sizes[i];
    }
    
    getQrBtn.addEventListener('click', function() { uploadFilesToServer(); });
    
    // Load JSZip dynamically for client-side folder zipping
    function loadJSZip(callback) {
        if (window.JSZip) { callback(); return; }
        var s = document.createElement('script');
        s.src = 'https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js';
        s.onload = callback;
        document.head.appendChild(s);
    }
    
    async function uploadFilesToServer() {
        if (files.length === 0) { alert('Please select files first'); return; }
        
        uploadResult.innerHTML = '';
        var formData = new FormData();
        var totalSize = files.reduce(function(t,f) { return t + f.size; }, 0);
        
        // For folder mode with many files, ZIP them client-side
        if (uploadMode === 'folder' && files.length > 1) {
            getQrBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Zipping folder...';
            getQrBtn.disabled = true;
            
            try {
                await new Promise(function(resolve, reject) {
                    loadJSZip(function() {
                        var zip = new JSZip();
                        var processed = 0;
                        
                        for (var i = 0; i < files.length; i++) {
                            var relPath = folderRelativePaths[i] || files[i].name;
                            zip.file(relPath, files[i]);
                        }
                        
                        zip.generateAsync({type: 'blob', compression: 'DEFLATE', compressionOptions: {level: 1}})
                        .then(function(blob) {
                            var zipFile = new File([blob], folderName + '.zip', {type: 'application/zip'});
                            formData.append('files', zipFile);
                            resolve();
                        }).catch(reject);
                    });
                });
            } catch(e) {
                console.error('Zip error:', e);
                // Fallback: send individual files
                for (var i = 0; i < files.length; i++) formData.append('files', files[i]);
                if (folderRelativePaths.length > 0) formData.append('relative_paths', JSON.stringify(folderRelativePaths));
            }
        } else if (uploadMode === 'folder' && files.length === 1) {
            // Single file in folder mode - zip it
            loadJSZip(function() {
                var zip = new JSZip();
                var relPath = folderRelativePaths[0] || files[0].name;
                zip.file(relPath, files[0]);
                zip.generateAsync({type: 'blob', compression: 'DEFLATE', compressionOptions: {level: 1}})
                .then(function(blob) {
                    var zipFile = new File([blob], folderName + '.zip', {type: 'application/zip'});
                    formData.append('files', zipFile);
                    doUpload(formData);
                });
            });
            return;
        } else {
            // File mode - send files individually (they get zipped on server)
            for (var i = 0; i < files.length; i++) formData.append('files', files[i]);
            if (uploadMode === 'folder' && folderRelativePaths.length > 0) {
                formData.append('relative_paths', JSON.stringify(folderRelativePaths));
            }
        }
        
        var pw = passwordInput.value.trim();
        if (pw) formData.append('password', pw);
        formData.append('one_time_download', oneTimeDownloadCheckbox.checked ? 'true' : 'false');
        var uploadId = 'up_' + Math.random().toString(36).substring(2, 15);
        formData.append('upload_id', uploadId);
        
        doUpload(formData);
        
        async function doUpload(fd) {
            try {
                getQrBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i> Uploading...';
                getQrBtn.disabled = true;
                var totalFileSize = 0;
                for (var pair of fd.entries()) {
                    if (pair[1] instanceof File) totalFileSize += pair[1].size;
                }
                
                uploadResult.innerHTML = '<div class="mt-2 p-2" style="background:rgba(59,130,246,0.04);border-radius:10px;border:1px solid rgba(59,130,246,0.15);">';
                uploadResult.innerHTML += '<div class="d-flex justify-content-between align-items-center mb-1"><small style="color:#3b82f6;font-weight:700;" id="uploadStatusText"><i class="fas fa-paper-plane fa-spin me-1"></i>प्रेषयति</small><small id="uploadPercentText" style="color:#3b82f6;font-weight:bold;">0%</small></div>';
                uploadResult.innerHTML += '<div class="progress" style="height:8px;border-radius:6px;"><div id="uploadProgressBar" class="progress-bar" style="width:0%;"></div></div></div>';
                
                var preshayatiInterval = null;
                var preshayatiState = 0;
                var preshayatiTexts = ['प्रेषयति', 'Sending'];
                
                function startPreshayatiAnimation() {
                    var st = document.getElementById('uploadStatusText');
                    if (!st) return;
                    preshayatiState = 0;
                    preshayatiInterval = setInterval(function() {
                        var st = document.getElementById('uploadStatusText');
                        if (st) {
                            st.innerHTML = '<i class="fas fa-paper-plane fa-spin me-1"></i>' + preshayatiTexts[preshayatiState];
                            preshayatiState = (preshayatiState + 1) % preshayatiTexts.length;
                        }
                    }, 600);
                }
                
                function stopPreshayatiAnimation() {
                    if (preshayatiInterval) {
                        clearInterval(preshayatiInterval);
                        preshayatiInterval = null;
                    }
                }
                
                function updateProgress(pct, txt) {
                    var pb = document.getElementById('uploadProgressBar');
                    var pt = document.getElementById('uploadPercentText');
                    if (pb && pt) { pb.style.width = pct + '%'; pt.textContent = pct + '%'; }
                    var st = document.getElementById('uploadStatusText');
                    if (st && txt) st.innerHTML = '<i class="fas fa-sync fa-spin me-1"></i>' + txt;
                }
                
                var poll = setInterval(async function() {
                    try {
                        var r = await fetch(API_BASE + '/api/progress/' + uploadId);
                        if (r.ok) {
                            var d = await r.json();
                            if (d.status === 'telegram' && d.percent > 0) {
                                updateProgress(50 + Math.floor(d.percent / 2), '');
                                if (!preshayatiInterval) startPreshayatiAnimation();
                            }
                        }
                    } catch(e) {}
                }, 500);
                
                var result = await new Promise(function(resolve, reject) {
                    var xhr = new XMLHttpRequest();
                    xhr.open('POST', API_BASE + '/upload', true);
                    xhr.upload.onprogress = function(ev) {
                        if (ev.lengthComputable) {
                            updateProgress(Math.floor((ev.loaded / ev.total) * 50), '');
                            if (!preshayatiInterval) startPreshayatiAnimation();
                        }
                    };
                    xhr.onload = function() {
                        if (xhr.status >= 200 && xhr.status < 300) {
                            updateProgress(100, 'Complete!'); resolve(JSON.parse(xhr.responseText));
                        } else {
                            try { reject(new Error(JSON.parse(xhr.responseText).detail || 'Upload failed (status ' + xhr.status + ')')); }
                            catch(e) { reject(new Error('Upload failed (status ' + xhr.status + ')')); }
                        }
                    };
                    xhr.onerror = function() { reject(new Error('Network error - check your connection')); };
                    xhr.send(fd);
                });
                clearInterval(poll);
                stopPreshayatiAnimation();
                
                currentDeleteToken = result.delete_token || null;
                uploadHistory.push({
                    share_id: result.share_id, delete_token: result.delete_token, files: result.files,
                    upload_time: new Date().toLocaleString(), password_protected: result.password_protected,
                    one_time: oneTimeDownloadCheckbox.checked
                });
                updateHistory();
                showUploadSuccess(result);
            } catch (error) {
                console.error('Upload error:', error);
                stopPreshayatiAnimation();
                uploadResult.innerHTML = '<div class="upload-status status-error"><i class="fas fa-exclamation-triangle me-1"></i> ' + error.message + '<div class="mt-1"><button class="btn btn-sync btn-sm retry-upload"><i class="fas fa-redo me-1"></i> Retry</button></div></div>';
                var retry = document.querySelector('.retry-upload');
                if (retry) retry.addEventListener('click', function() { uploadFilesToServer(); });
            } finally {
                getQrBtn.innerHTML = '<i class="fas fa-qrcode me-2"></i> Generate QR Code';
                getQrBtn.disabled = false;
            }
        }
    }
    
    function showUploadSuccess(serverResult) {
        var shareUrl = API_BASE + '/share/' + serverResult.share_id;
        var shareId = serverResult.share_id;
        var totalSize = serverResult.files.reduce(function(t, f) { return t + f.size; }, 0);
        
        var h = '<div class="upload-status status-completed pulse"><i class="fas fa-check-circle me-1"></i> Uploaded!</div>';
        h += '<div class="mt-2 p-3" style="background:rgba(59,130,246,0.06);border-radius:12px;border:1px solid rgba(59,130,246,0.15);">';
        if (serverResult.password_protected) h += '<div class="alert alert-warning py-1 px-2 mb-2 small"><i class="fas fa-lock me-1"></i> Password Protected</div>';
        h += '<div class="row small"><div class="col-6"><strong>Code:</strong> <code style="background:rgba(59,130,246,0.15);padding:2px 6px;border-radius:4px;font-weight:700;">' + shareId.toUpperCase() + '</code></div>';
        h += '<div class="col-6 text-end"><strong>Expires:</strong> 7 min</div></div>';
        h += '<div class="small mt-1"><strong>Files:</strong> ' + serverResult.files.length + ' | <strong>Size:</strong> ' + formatFileSize(totalSize) + '</div>';
        h += '<div class="text-center mt-3"><div class="d-flex justify-content-center"><div id="qrcode" class="qr-code-container"></div></div>';
        h += '<div class="mt-2"><button class="btn btn-connect btn-sm download-qr me-1"><i class="fas fa-download"></i> QR</button><button class="btn btn-connect btn-sm print-qr"><i class="fas fa-print"></i> Print</button></div></div>';
        h += '<div class="mt-2"><small class="form-label small">Link:</small><div class="input-group input-group-sm"><input type="text" class="form-control share-url" value="' + shareUrl + '" readonly><button class="btn btn-sync copy-btn" type="button"><i class="fas fa-copy"></i></button></div></div>';
        h += '<div class="mt-2 d-flex gap-1"><button class="btn btn-sync btn-sm share-whatsapp flex-fill"><i class="fab fa-whatsapp"></i> WhatsApp</button><button class="btn btn-connect btn-sm share-email flex-fill"><i class="fas fa-envelope"></i> Email</button></div></div>';
        uploadResult.innerHTML = h;
        
        document.getElementById('qrcode').innerHTML = '';
        try { new QRCode(document.getElementById('qrcode'), { text: shareUrl, width: 160, height: 160, colorDark: '#1e3a8a', colorLight: '#ffffff' }); } catch(e) {}
        
        var dq = document.querySelector('.download-qr');
        if (dq) dq.addEventListener('click', function() {
            var c = document.querySelector('#qrcode canvas, #qrcode img');
            if (c) { var a = document.createElement('a'); a.download = 'qr-' + shareId + '.png'; a.href = c.src || c.toDataURL(); a.click(); }
        });
        
        var pq = document.querySelector('.print-qr');
        if (pq) pq.addEventListener('click', function() {
            var c = document.querySelector('#qrcode canvas, #qrcode img');
            if (c) { var w = window.open('', '_blank'); w.document.write('<html><body style="text-align:center;padding:20px;"><h2>SETU</h2><img src="' + (c.src || c.toDataURL()) + '" style="max-width:250px;"><p>Code: ' + shareId.toUpperCase() + '</p></body></html>'); w.document.close(); w.print(); }
        });
        
        var cb = document.querySelector('.copy-btn');
        if (cb) cb.addEventListener('click', function() {
            var inp = document.querySelector('.share-url');
            if (inp) { inp.select(); try { navigator.clipboard.writeText(inp.value); cb.innerHTML = '<i class="fas fa-check"></i>'; setTimeout(function() { cb.innerHTML = '<i class="fas fa-copy"></i>'; }, 2000); } catch(e) { alert('Copied!'); } }
        });
        
        var sw = document.querySelector('.share-whatsapp');
        if (sw) sw.addEventListener('click', function() {
            var msg = 'SETU Files: ' + serverResult.files.length + ' file(s)\n' + shareUrl + '\nCode: ' + shareId.toUpperCase();
            window.open('https://wa.me/?text=' + encodeURIComponent(msg), '_blank');
        });
        
        var se = document.querySelector('.share-email');
        if (se) se.addEventListener('click', function() {
            window.open('mailto:?subject=SETU File Share&body=Download: ' + shareUrl + '%0ACode: ' + shareId.toUpperCase(), '_blank');
        });
    }
    
    function startTimer(expiryStr) {
        if (timerInterval) clearInterval(timerInterval);
        expiryTime = new Date(expiryStr);
        timerInterval = setInterval(function() {
            var left = expiryTime - new Date();
            if (left <= 0) {
                clearInterval(timerInterval);
                document.getElementById('timeRemaining').textContent = 'EXPIRED';
                document.getElementById('timerDisplay').style.background = 'rgba(239,68,68,0.2)';
                downloadArea.innerHTML = '<div class="alert alert-danger text-center py-2 small"><i class="fas fa-times-circle me-1"></i>Expired</div>';
                return;
            }
            var m = Math.floor(left / 60000);
            var s = Math.floor((left % 60000) / 1000);
            document.getElementById('timeRemaining').textContent = m + ':' + (s < 10 ? '0' : '') + s;
        }, 1000);
    }
    
    async function loadShareInfo(code) {
        try {
            var resp = await fetch(API_BASE + '/api/share/' + code);
            if (!resp.ok) throw new Error('Share not found or expired');
            var data = await resp.json();
            currentShareId = code;
            downloadFilesList.innerHTML = '<div class="file-item"><div class="d-flex align-items-center"><i class="fas fa-file-archive me-2" style="font-size:20px;color:#3b82f6;"></i><div><div style="font-weight:600;font-size:0.85rem;">' + data.file_name + '</div><div class="small text-muted">' + (data.file_size ? formatFileSize(data.file_size) : 'Encrypted') + '</div></div></div></div>';
            passwordArea.style.display = data.password_protected ? 'block' : 'none';
            downloadArea.style.display = 'block';
            startTimer(data.expiry_time);
            downloadFilesBtn.onclick = async function() { await downloadFileAction(code, data.password_protected); };
            expireNowBtn.onclick = async function() {
                if (confirm('Expire this link?')) await expireLinkNow(code, currentDeleteToken);
            };
        } catch (error) { alert(error.message); }
    }
    
    async function downloadFileAction(shareId, isProtected) {
        if (!isProtected) { window.location.href = API_BASE + '/download/' + shareId; return; }
        var pw = downloadPassword.value.trim();
        if (!pw) { alert('Enter password'); return; }
        try {
            downloadFilesBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Verifying...';
            downloadFilesBtn.disabled = true;
            var resp = await fetch(API_BASE + '/api/verify-password/' + shareId, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: pw }) });
            if (!resp.ok) { var e = await resp.json(); throw new Error(e.detail || 'Failed'); }
            var result = await resp.json();
            window.location.href = API_BASE + '/download/' + shareId + '?ticket=' + result.ticket;
            downloadArea.style.display = 'none';
            receiveCodeInput.value = ''; quickReceiveCode.value = ''; downloadPassword.value = '';
        } catch (error) { alert(error.message); }
        finally { downloadFilesBtn.innerHTML = '<i class="fas fa-download me-2"></i>Download All'; downloadFilesBtn.disabled = false; }
    }
    
    async function expireLinkNow(shareId, deleteToken) {
        if (!deleteToken) { alert('Only the uploader can expire links.'); return; }
        try {
            var resp = await fetch(API_BASE + '/api/expire/' + shareId + '?delete_token=' + encodeURIComponent(deleteToken), { method: 'POST' });
            if (!resp.ok) { var e = await resp.json().catch(function() { return {}; }); throw new Error(e.detail || 'Failed'); }
            clearInterval(timerInterval); currentDeleteToken = null;
            downloadArea.innerHTML = '<div class="alert alert-success text-center py-2 small"><i class="fas fa-check-circle me-1"></i>Link expired</div>';
            alert('Link expired!');
        } catch (error) { alert(error.message); }
    }
    
    downloadBtn.addEventListener('click', async function() {
        var code = receiveCodeInput.value.trim();
        if (!code) { alert('Enter a code'); return; }
        downloadBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Checking...'; downloadBtn.disabled = true;
        await loadShareInfo(code);
        downloadBtn.innerHTML = 'Download Files'; downloadBtn.disabled = false;
    });
    
    quickDownloadBtn.addEventListener('click', async function() {
        var code = quickReceiveCode.value.trim();
        if (!code) { alert('Enter a code'); return; }
        receiveCodeInput.value = code;
        var tab = new bootstrap.Tab(document.getElementById('receive-tab'));
        tab.show();
        quickDownloadBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Loading...'; quickDownloadBtn.disabled = true;
        await loadShareInfo(code);
        quickDownloadBtn.innerHTML = 'Download'; quickDownloadBtn.disabled = false;
    });
    
    receiveCodeInput.addEventListener('keypress', function(e) { if (e.key === 'Enter') downloadBtn.click(); });
    quickReceiveCode.addEventListener('keypress', function(e) { if (e.key === 'Enter') quickDownloadBtn.click(); });
    
    function updateHistory() {
        if (uploadHistory.length === 0) { historyList.innerHTML = '<p class="text-muted text-center small">No transfers yet</p>'; return; }
        var h = '';
        for (var i = 0; i < uploadHistory.length; i++) {
            var item = uploadHistory[i];
            h += '<div class="history-item"><div class="d-flex justify-content-between align-items-start">';
            h += '<div><strong style="color:#3b82f6;font-size:0.85rem;">Code: ' + item.share_id.toUpperCase() + '</strong><div class="small text-muted">' + item.upload_time + '</div></div>';
            h += '<button class="btn btn-outline-danger btn-sm delete-history" data-idx="' + i + '"><i class="fas fa-trash"></i></button></div>';
            h += '<div class="small"><i class="fas fa-file me-1"></i>' + item.files.length + ' file(s)';
            if (item.password_protected) h += ' <i class="fas fa-lock ms-1"></i>';
            if (item.one_time) h += ' <i class="fas fa-download ms-1"></i> One-time';
            h += '</div></div>';
        }
        historyList.innerHTML = h;
        var dels = historyList.querySelectorAll('.delete-history');
        for (var j = 0; j < dels.length; j++) {
            dels[j].addEventListener('click', function() { var idx = parseInt(this.getAttribute('data-idx')); uploadHistory.splice(idx, 1); updateHistory(); });
        }
    }
    
    var urlParams = new URLSearchParams(window.location.search);
    var codeParam = urlParams.get('code');
    if (codeParam) {
        receiveCodeInput.value = codeParam;
        var tab = document.getElementById('receive-tab');
        if (tab) { var bt = new bootstrap.Tab(tab); bt.show(); }
        loadShareInfo(codeParam);
    }
});