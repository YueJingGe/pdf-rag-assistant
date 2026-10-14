import React, { useEffect, useState, useRef } from 'react';
import { Drawer, Spin, Typography, Empty, Tag } from 'antd';
import { FileTextOutlined } from '@ant-design/icons';
import { documentApi } from '../../services/api';
import styles from './index.module.less';

interface Props {
  open: boolean;
  onClose: () => void;
  knowledgeBaseId: number | null;
  filename: string;
  snippet: string;
  page: number;
}

export default function DocumentViewer({ open, onClose, knowledgeBaseId, filename, snippet, page }: Props) {
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [docFilename, setDocFilename] = useState('');
  const highlightRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open || !knowledgeBaseId || !filename) return;

    const fetchContent = async () => {
      setLoading(true);
      try {
        // Try by source_filename first (handles UUID-prefixed filenames from vector store)
        const { data } = await documentApi.getContentBySource(knowledgeBaseId, filename);
        setContent(data.content);
        setDocFilename(data.filename);
      } catch {
        // Fallback: try matching by document list
        try {
          const { data: docs } = await documentApi.list(knowledgeBaseId);
          const targetDoc = docs.find((d) => filename.includes(d.filename) || d.filename.includes(filename));
          if (targetDoc) {
            const { data } = await documentApi.getContent(knowledgeBaseId, targetDoc.id);
            setContent(data.content);
            setDocFilename(data.filename);
          } else {
            setContent('');
            setDocFilename(filename);
          }
        } catch {
          setContent('');
        }
      } finally {
        setLoading(false);
      }
    };
    fetchContent();
  }, [open, knowledgeBaseId, filename]);

  // Scroll to highlighted section after content loads
  useEffect(() => {
    if (content && highlightRef.current) {
      setTimeout(() => {
        highlightRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 100);
    }
  }, [content, snippet]);

  // 归一化定位：OCR 文本含连续空格/换行/字间空格，且引用链路可能引入全半角标点差异，
  // 裸 indexOf 必然失配（md 能命中、扫描件 PDF 永远不中的根因）。
  // 把 content 折叠到强归一化空间（去空白 + 去标点，只留语义字符）后与 snippet 同规则匹配，
  // 再经 map 数组映射回原串位置切片高亮。
  const locateSnippet = (source: string, target: string): [number, number] | null => {
    // 防御：剔除回答正文里附带的引用标注尾巴
    const cleaned = target.replace(/\s*\[来源:[^\]]*\]\s*/g, ' ');
    const parts: string[] = [];
    const map: number[] = [];
    for (let i = 0; i < source.length; i++) {
      const ch = source[i];
      if (/\s/.test(ch)) continue;
      // 全半角标点一律不参与匹配（两侧同规则，不影响定位语义）
      if (/[\p{P}\p{S}]/u.test(ch)) continue;
      parts.push(ch);
      map.push(i);
    }
    const norm = parts.join('');

    const probeRaw = cleaned.replace(/[\p{P}\p{S}\s]/gu, '');
    let probe = probeRaw.slice(0, 60);
    let idx = norm.indexOf(probe);
    if (idx === -1) {
      probe = probeRaw.slice(0, 30);
      idx = norm.indexOf(probe);
    }
    if (idx === -1 || probe.length === 0) return null;

    const start = map[idx];
    const end = map[Math.min(idx + probe.length - 1, map.length - 1)] + 1;
    return [start, end];
  };

  const renderContent = () => {
    if (loading) return <Spin style={{ display: 'block', margin: '40px auto' }} />;
    if (!content) return <Empty description="无法加载文档内容" />;

    const range = locateSnippet(content, snippet);
    if (!range) {
      return (
        <div className={styles.docContent}>
          <pre className={styles.preText}>{content}</pre>
        </div>
      );
    }

    const [start, end] = range;
    return (
      <div className={styles.docContent}>
        <pre className={styles.preText}>
          {content.slice(0, start)}
          <span ref={highlightRef} className={styles.highlight}>{content.slice(start, end)}</span>
          {content.slice(end)}
        </pre>
      </div>
    );
  };

  return (
    <Drawer
      title={
        <span>
          <FileTextOutlined style={{ marginRight: 8 }} />
          {docFilename || filename}
          <Tag color="geekblue" style={{ marginLeft: 8 }}>第 {page} 页</Tag>
        </span>
      }
      open={open}
      onClose={onClose}
      width={600}
      destroyOnClose
    >
      {renderContent()}
    </Drawer>
  );
}
