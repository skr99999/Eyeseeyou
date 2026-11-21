package org.eyeseeyou.edge;

import android.Manifest;
import android.app.Activity;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.WindowInsets;
import android.webkit.MimeTypeMap;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import java.io.IOException;

public final class MainActivity extends Activity {
    private static final String ASSET_HOST = "appassets.androidplatform.net";
    private static final String ASSET_PREFIX = "/assets/";
    private static final int CAMERA_PERMISSION = 1;

    private WebView web;
    private PermissionRequest pendingCamera;
    private boolean requestingCamera;

    private static boolean isAssetOrigin(Uri uri) {
        return "https".equals(uri.getScheme()) && ASSET_HOST.equals(uri.getEncodedAuthority());
    }

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        web = new WebView(this);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setAllowFileAccess(false);
        web.getSettings().setAllowContentAccess(false);
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                String[] resources = request.getResources();
                if (!isAssetOrigin(request.getOrigin()) || resources.length != 1
                        || !PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(resources[0])
                        || pendingCamera != null) {
                    request.deny();
                    return;
                }

                if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                    request.grant(resources);
                    return;
                }
                pendingCamera = request;
                if (!requestingCamera) {
                    requestingCamera = true;
                    requestPermissions(new String[]{Manifest.permission.CAMERA}, CAMERA_PERMISSION);
                }
            }

            @Override
            public void onPermissionRequestCanceled(PermissionRequest request) {
                if (pendingCamera == request) {
                    pendingCamera = null;
                }
            }
        });
        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                Uri url = request.getUrl();
                String path = url.getPath();
                if (!isAssetOrigin(url)
                        || path == null || !path.startsWith(ASSET_PREFIX)) {
                    return null;
                }

                String file = path.substring(ASSET_PREFIX.length());
                try {
                    String extension = MimeTypeMap.getFileExtensionFromUrl(url.toString());
                    String mime = MimeTypeMap.getSingleton().getMimeTypeFromExtension(extension);
                    if ("js".equals(extension) || "mjs".equals(extension)) {
                        mime = "text/javascript";
                    } else if ("json".equals(extension)) {
                        mime = "application/json";
                    } else if ("wasm".equals(extension)) {
                        mime = "application/wasm";
                    }
                    return new WebResourceResponse(mime == null ? "application/octet-stream" : mime,
                            null, getAssets().open(file));
                } catch (IOException missingAsset) {
                    return new WebResourceResponse("text/plain", "UTF-8", 404, "Not Found", null, null);
                }
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return true;
            }
        });

        FrameLayout root = new FrameLayout(this);
        if (Build.VERSION.SDK_INT >= 35) {
            root.setOnApplyWindowInsetsListener((view, insets) -> {
                android.graphics.Insets safe = insets.getInsets(
                        WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout()
                        | WindowInsets.Type.ime());
                view.setPadding(safe.left, safe.top, safe.right, safe.bottom);
                return insets;
            });
        }
        root.addView(web, new FrameLayout.LayoutParams(-1, -1));
        setContentView(root);
        web.loadUrl("https://" + ASSET_HOST + ASSET_PREFIX + "index.html");
    }

    @Override
    protected void onStop() {
        web.evaluateJavascript("document.dispatchEvent(new Event('eyeseeyou:background'));", null);
        super.onStop();
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] permissions, int[] grants) {
        super.onRequestPermissionsResult(code, permissions, grants);
        if (code == CAMERA_PERMISSION) {
            requestingCamera = false;
            PermissionRequest request = pendingCamera;
            pendingCamera = null;
            if (request != null) {
                if (grants.length == 1 && grants[0] == PackageManager.PERMISSION_GRANTED) {
                    request.grant(new String[]{PermissionRequest.RESOURCE_VIDEO_CAPTURE});
                } else {
                    request.deny();
                }
            }
        }
    }
}
