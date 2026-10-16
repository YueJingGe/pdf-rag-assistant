import React, { useEffect, useRef, useState } from "react";
import { Modal, Tag, Progress, Button, message } from "antd";
import { documentApi } from "../../services/api";

interface UploadingItem {
  filename: string;
  progress: number;
  status: "uploading" | "processing" | "done" | "error";
}

interface Props {
  kbId: number;
  /** 上传目标目录（null = 根/未归类） */
  categoryId: number | null;
  /** 待上传文件（父组件经隐藏 input 选完后传入） */
  files: File[];
  open: boolean;
  onClose: () => void;
  /** 上传请求全部发出后回调（父组件刷新树/侧栏计数） */
  onUploaded: () => void;
}

/**
 * P0-4 第三轮：轻量上传浮层（乐享式「⬆ 上传」按钮直达，替代文档管理 tab 的 Dragger）。
 * 收拢原 DocumentUpload 的上传 + 状态轮询逻辑：
 * 选完文件 → 逐个上传 → 轮询解析/向量化状态直到全部终态 → 「完成」可关闭。
 */
export default function UploadModal({ kbId, categoryId, files, open, onClose, onUploaded }: Props) {
  const [items, setItems] = useState<UploadingItem[]>([]);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const patch = (filename: string, fields: Partial<UploadingItem>) =>
    setItems((prev) => prev.map((f) => (f.filename === filename ? { ...f, ...fields } : f)));

  const busy = items.some((f) => f.status === "uploading" || f.status === "processing");

  useEffect(() => {
    if (!open || files.length === 0) return;

    setItems(files.map((f) => ({ filename: f.name, progress: 0, status: "uploading" })));

    (async () => {
      for (const file of files) {
        try {
          patch(file.name, { progress: 30 });
          await documentApi.upload(kbId, file, categoryId);
          patch(file.name, { progress: 100, status: "processing" });
        } catch {
          patch(file.name, { progress: 100, status: "error" });
          message.error(`${file.name} 上传失败`);
        }
      }
      onUploaded();

      // 轮询解析/向量化状态直到全部终态（ready/error）
      pollingRef.current = setInterval(async () => {
        try {
          const { data: docs } = await documentApi.list(kbId);
          setItems((prev) => {
            const next = prev.map((f) => {
              if (f.status !== "processing") return f;
              const doc = docs.find((d) => d.filename === f.filename);
              if (!doc) return f;
              const nextStatus: UploadingItem["status"] =
                doc.status === "ready" ? "done" : doc.status === "error" ? "error" : "processing";
              return {
                ...f,
                status: nextStatus,
              };
            });
            const stillBusy = next.some((f) => f.status === "uploading" || f.status === "processing");
            if (!stillBusy && pollingRef.current) {
              clearInterval(pollingRef.current);
              pollingRef.current = null;
            }
            return next;
          });
        } catch {
          // 轮询失败忽略，下一轮重试
        }
      }, 2000);
    })();

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, files]);

  const statusTag = (status: UploadingItem["status"]) => {
    const map: Record<UploadingItem["status"], { color: string; text: string }> = {
      uploading: { color: "blue", text: "上传中" },
      processing: { color: "geekblue", text: "解析/向量化中" },
      done: { color: "green", text: "完成" },
      error: { color: "red", text: "失败" },
    };
    const item = map[status];
    return <Tag color={item.color}>{item.text}</Tag>;
  };

  return (
    <Modal
      title={`上传到知识库${busy ? "" : "（已完成）"}`}
      open={open}
      closable={false}
      maskClosable={false}
      keyboard={false}
      footer={[
        <Button key="close" type="primary" size="small" disabled={busy} onClick={onClose}>
          {busy ? "上传处理中…" : "完成"}
        </Button>,
      ]}
    >
      {items.map((item, idx) => (
        <div key={`${item.filename}-${idx}`} style={{ marginBottom: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 13, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {item.filename}
            </span>
            {statusTag(item.status)}
          </div>
          <Progress
            percent={item.progress}
            size="small"
            status={item.status === "error" ? "exception" : item.status === "done" ? "success" : "active"}
            showInfo={false}
          />
        </div>
      ))}
    </Modal>
  );
}
