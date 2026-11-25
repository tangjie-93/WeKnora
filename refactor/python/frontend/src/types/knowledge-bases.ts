import type { ComputedRef, Ref } from 'vue';
import type { UseQueryReturnType } from '@tanstack/vue-query';
import type { CurrentAccountView } from './auth';

export type KnowledgeBaseCreator = 'all' | 'mine' | 'others';
export interface CreateKnowledgeBaseInput {
    name: string;
    description?: string;
    type?: 'document' | '';
    embedding_model_id?: '';
    summary_model_id?: '';
}
export interface KnowledgeBaseChunkingConfig {
    chunk_size: number;
    chunk_overlap: number;
    separators: string[] | null;
}
export interface KnowledgeBaseVlmConfig {
    enabled: boolean;
    model_id: string;
    model_name: string;
    base_url: string;
    api_key: string;
    interface_type: string;
}
export interface KnowledgeBaseAsrConfig { enabled: boolean; model_id: string; language: string }
export interface KnowledgeBaseStorageConfig {
    secret_id: string;
    secret_key: string;
    region: string;
    bucket_name: string;
    app_id: string;
    path_prefix: string;
    provider: string;
}
export interface KnowledgeBaseIndexingStrategy {
    vector_enabled: boolean;
    keyword_enabled: boolean;
    wiki_enabled: boolean;
    graph_enabled: boolean;
}
export interface KnowledgeBaseCapabilities {
    vector: boolean;
    keyword: boolean;
    wiki: boolean;
    graph: boolean;
    faq: boolean;
}
export interface KnowledgeBaseView {
    id: string;
    name: string;
    type: 'document';
    description: string;
    tenant_id: number;
    creator_id: string;
    is_temporary: false;
    created_at: string;
    updated_at: string;
    deleted_at: null;
    chunking_config: KnowledgeBaseChunkingConfig;
    image_processing_config: { model_id: string };
    embedding_model_id: '';
    summary_model_id: '';
    vlm_config: KnowledgeBaseVlmConfig;
    asr_config: KnowledgeBaseAsrConfig;
    storage_provider_config: { provider: string } | null;
    storage_config: KnowledgeBaseStorageConfig;
    indexing_strategy: KnowledgeBaseIndexingStrategy;
    extract_config: null;
    faq_config: null;
    question_generation_config: null;
    auto_tag_config: null;
    wiki_config: null;
    profile_config: null;
    vector_store_id?: string;
    storage_backend_id?: string;
    knowledge_count: number;
    chunk_count: number;
    is_processing: boolean;
    processing_count: number;
    share_count: number;
    is_pinned: boolean;
    pinned_at: string | null;
    creator_name?: string;
    capabilities: KnowledgeBaseCapabilities;
    vector_store_source: 'unavailable';
    vector_store_status: 'unavailable';
}
export type KnowledgeBaseQueryKey = readonly ['knowledge-bases', number, string, number, KnowledgeBaseCreator];
export interface KnowledgeBaseOwnership {
    epoch: number;
    userID: string;
    tenantID: number;
    creator: KnowledgeBaseCreator;
    generation: number;
}
export interface UseKnowledgeBasesReturn {
    account: CurrentAccountView['account'];
    accountQuery: CurrentAccountView['query'];
    listQuery: UseQueryReturnType<KnowledgeBaseView[], Error>;
    items: ComputedRef<KnowledgeBaseView[]>;
    canCreate: ComputedRef<boolean>;
    creator: Ref<KnowledgeBaseCreator>;
    submit: (input: CreateKnowledgeBaseInput) => Promise<boolean>;
    isSubmitting: Ref<boolean>;
    submitError: Ref<string>;
    retryList: () => Promise<void>;
    clearDraftState: () => void;
}
export interface CreateKnowledgeBaseDialogProps {
    modelValue: boolean;
    isSubmitting: boolean;
    submitError: string;
    canCreate: boolean;
    submit: (input: CreateKnowledgeBaseInput) => Promise<boolean>;
}
export interface CreateKnowledgeBaseDialogEmits { 'update:modelValue': [value: boolean] }
