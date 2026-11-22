"""Генератор Lua 5.1-скрипта квестов ``gamedata/scripts/<mod>_quests.script``.

Модуль реализует ``[4] RENDER`` для Lua-слоя и строго следует
``standart_of_auto.md`` (2.2 и 2.3):

* все данные квестов лежат в статической таблице ``local QUESTS``;
* игровые функции объявляются ``local`` и регистрируются **плоскими**
  ключами в ``task_functor``, ``task_status_functor``, ``xr_effects`` и
  ``dialogs``;
* функции-условия и эффекты имеют каноническую сигнатуру
  ``function(actor, npc, p)``;
* ``register()`` вызывается на ``on_game_start``, ``on_game_load`` и
  ``actor_on_first_update``, чтобы восстановиться после загрузки сейва;
* никакого ``start_dialogs``/динамической инъекции диалогов нет — диалоги
  привязываются декларативно в ``character_desc_<level>.xml``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable, Sequence

from src.core.models import (
    ClearSmart,
    CompleteTask,
    DontHasInfo,
    GiveInfo,
    GiveItem,
    GiveMoney,
    GiveTask,
    HasInfo,
    HasItem,
    HasMoney,
    RemoveInfo,
    RemoveItem,
    RemoveSquad,
    SetTarget,
    SmartOwner,
    SpawnNpcItem,
    SpawnSquad,
    TakeItem,
    TakeMoney,
    phrase_action_mode,
)
from src.logger import get_logger

if TYPE_CHECKING:
    from src.core.models import Condition, Dialog, ModProject, Quest, Stage

logger = get_logger("compiler.lua_gen")

#: Имя таблицы-модуля, которое печатается в логах и комментарии шапки.
DEFAULT_SCRIPT_NAME = "quests"
#: Звук выдачи/обновления задачи (PDA).
DEFAULT_PDA_SOUND = "pda_task"
#: Троттлинг status_functor в миллисекундах (эталон — 3000).
DEFAULT_STATUS_THROTTLE_MS = 3000
#: Радиус «игрок подошёл к квестодателю» в метрах (эталон — 40).
DEFAULT_RETURN_DISTANCE = 40.0
#: Запасная иконка PDA, если в модели не задана своя.
DEFAULT_ICON = "ui_inGame2_Put_v_pripyat"
#: Запасной приоритет задачи в PDA.
DEFAULT_PRIOR = 60
#: Типы Lua-таблиц, в которые регистрируются плоские функции.
ENGINE_TABLES = ("task_functor", "task_status_functor", "xr_effects", "dialogs")
#: Зарезервированные слова Lua 5.1, которые нельзя использовать как ключи
#: таблицы без скобок.
_LUA_RESERVED = frozenset(
    {
        "and",
        "break",
        "do",
        "else",
        "elseif",
        "end",
        "false",
        "for",
        "function",
        "if",
        "in",
        "local",
        "nil",
        "not",
        "or",
        "repeat",
        "return",
        "then",
        "true",
        "until",
        "while",
    }
)


_HELPERS_TEMPLATE = r"""
-- ============================================================================
-- Generic helpers (shared by every generated quest)
-- ============================================================================

local STATUS_THROTTLE_MS = __STATUS_THROTTLE__
local RETURN_DISTANCE = __RETURN_DISTANCE__
local PDA_SOUND = "__PDA_SOUND__"
local registered = false

-- Safe pstor read; returns def when the actor is not available yet.
local function vget(key, def)
	if not db.actor then return def end
	return load_var(db.actor, key, def)
end

-- Safe pstor write; ignores calls before the actor exists.
local function vset(key, val)
	if not db.actor then return end
	save_var(db.actor, key, val)
end

-- Returns true only when Warfare mode is active.
local function is_warfare()
	return (IsWarfare and IsWarfare()) or false
end

-- Returns true when the actor belongs to the requested technical faction.
-- Mirrors the reference is_actor_army(): warfare.actor_faction first, then
-- the true community (works outside Warfare as well).
local function is_actor_faction(faction)
	if not faction or faction == "" then return false end
	if warfare and warfare.actor_faction == faction then
		return true
	end
	local ok, comm = pcall(function() return get_actor_true_community() end)
	return (ok and comm == faction) or false
end

-- Resolves a SIMBOARD smart-terrain by its technical name.
local function get_smart(name)
	if not name or name == "" then return nil end
	if not (SIMBOARD and SIMBOARD.smarts_by_names) then return nil end
	return SIMBOARD.smarts_by_names[name]
end

-- Resolves a stage target: smart name, numeric server id or story id.
-- Story names are resolved through get_story_object_id(): the engine's
-- story_object lookup expects a numeric story id, not a string name.
local function resolve_target(target)
	if target == nil or target == "" then return nil end
	local smart = get_smart(target)
	if smart then return smart.id end
	local numeric_id = tonumber(target)
	if numeric_id then
		local obj = alife_object(numeric_id)
		return obj and obj.id or nil
	end
	if get_story_object_id then
		local ok, story_id = pcall(function()
			return get_story_object_id(target)
		end)
		if ok and story_id and story_id ~= 0 then
			local obj = alife_object(story_id)
			return obj and obj.id or story_id
		end
	end
	return nil
end

-- Stable pstor key; never equals task_id (task_manager clears that key).
local function stage_key(q, stage, suffix)
	return q.key_prefix .. "_v_" .. tostring(stage) .. "_" .. suffix
end

-- True when the squad still has at least one NPC.
local function squad_alive(id)
	if not id or id == 0 then return false end
	local squad = alife_object(id)
	if not squad then return false end
	local ok, count = pcall(function() return squad:npc_count() end)
	return ok and (count or 0) > 0
end

-- Counts items of one section in the actor inventory (stack-aware).
local function actor_item_count(section, actor)
	local obj = actor or db.actor
	if not (obj and section and section ~= "") then return 0 end
	local ok, total = pcall(function()
		local sum = 0
		obj:iterate_inventory(function(owner, item)
			if item and item:section() == section then
				local count = 1
				local counted, value = pcall(function() return item:count() end)
				if counted and value then count = value end
				sum = sum + count
			end
		end, nil)
		return sum
	end)
	if ok and total then return total end
	return obj:object(section) and 1 or 0
end

-- Returns the number of live NPCs in a squad-like object.
local function squad_npc_count(obj)
	if not obj then return 0 end
	local ok, count = pcall(function() return obj:npc_count() end)
	if ok and count then return count end
	return 0
end

-- Prefers a living squad when several objects share one section name.
local function prefer_squad(candidate, current)
	if not candidate then return current end
	if not current then return candidate end
	local candidate_alive = squad_npc_count(candidate) > 0
	local current_alive = squad_npc_count(current) > 0
	if candidate_alive and not current_alive then return candidate end
	return current
end

-- Resolves a numeric id, story id, squad section or server object section.
local function resolve_alife_object(target)
	if not target or target == "" then return nil end
	local numeric = tonumber(target)
	if numeric then return alife_object(numeric) end

	if get_story_object then
		local object_ok, story_obj = pcall(function()
			return get_story_object(target)
		end)
		if object_ok and story_obj then return story_obj end
	end
	if get_story_squad then
		local squad_ok, squad = pcall(function()
			return get_story_squad(target)
		end)
		if squad_ok and squad then return squad end
	end
	if get_story_object_id then
		local id_ok, story_id = pcall(function()
			return get_story_object_id(target)
		end)
		if id_ok and story_id and story_id ~= 0 then
			local obj = alife_object(story_id)
			if obj then return obj end
		end
	end

	local found = nil
	if SIMBOARD and SIMBOARD.squads then
		pcall(function()
			for _, squad in pairs(SIMBOARD.squads) do
				if squad and squad:section_name() == target then
					found = prefer_squad(squad, found)
				end
			end
		end)
		if found then return found end
	end

	pcall(function()
		local game = alife()
		if not game then return end
		game:iterate_objects(function(se_obj)
			if se_obj and se_obj:section_name() == target then
				found = prefer_squad(se_obj, found)
			end
		end)
	end)
	return found
end

-- True only after the target squad was seen alive and then lost all NPCs.
local function target_squad_dead(q, stage)
	local data = q and q.stages and q.stages[stage]
	local target = (data and data.target_squad) or ""
	if target == "" then return false end

	local seen_key = stage_key(q, stage, "target_seen")
	local squad = resolve_alife_object(target)
	if squad then
		vset(seen_key, 1)
		if squad.id and not alife_object(squad.id) then return true end
		return squad_npc_count(squad) <= 0
	end
	return vget(seen_key, 0) == 1
end

-- Withdraws money without going below zero.
local function take_money(amount, actor)
	local obj = actor or db.actor
	amount = tonumber(amount) or 0
	if not (obj and amount > 0) then return end

	local balance = 0
	local ok, value = pcall(function() return obj:money() end)
	if ok and value then balance = value end
	local delta = math.min(amount, balance)
	if delta > 0 then obj:give_money(-delta) end
end

-- Plays the PDA task sound once.
local function sound_task()
	if not (db.actor and xr_sound and xr_sound.set_sound_play) then return end
	pcall(xr_sound.set_sound_play, db.actor:id(), PDA_SOUND)
end

-- Shows a PDA tip by string id; ignores ids without a translation so the PDA
-- never displays raw technical identifiers.
local function pda_tip(text_id)
	if not text_id or text_id == "" then return end
	if not (db.actor and news_manager and news_manager.send_tip) then return end
	if game and game.translate_string then
		local ok, translated = pcall(game.translate_string, text_id)
		if not ok or not translated or translated == "" or translated == text_id then
			return
		end
	end
	pcall(news_manager.send_tip, db.actor, text_id, nil, "default", 5000)
end

-- Announces a stage exactly once and survives save/load.
local function announce(said_key, stage, text_id)
	if vget(said_key, 0) >= stage then return end
	vset(said_key, stage)
	sound_task()
	pda_tip(text_id)
end

-- Keeps a quest squad out of the offline combat simulation.
local function mark_task_squad(squad)
	if not (squad and sim_offline_combat and sim_offline_combat.task_squads) then
		return
	end
	sim_offline_combat.task_squads[squad.id] = true
end

-- Releases a squad id after the quest is finished or failed.
local function unmark_task_squad(id)
	if id and id ~= 0 and sim_offline_combat and sim_offline_combat.task_squads then
		sim_offline_combat.task_squads[id] = nil
	end
end

-- Releases every squad remembered for a quest.
local function unmark_quest_squads(q)
	if not q then return end
	for stage, data in pairs(q.stages) do
		unmark_task_squad(vget(stage_key(q, stage, "enemy"), 0))
		local allies = (data.capture and data.capture.ally_count) or 0
		for i = 1, allies do
			unmark_task_squad(vget(stage_key(q, stage, "ally" .. i), 0))
		end
	end
	-- Dynamic squads spawned by SpawnSquad in a dialog phrase or quest action.
	local dyn_count = vget(q.key_prefix .. "_dyn_squad_cnt", 0) or 0
	for i = 1, dyn_count do
		unmark_task_squad(
			vget(q.key_prefix .. "_dyn_squad_" .. tostring(i), 0)
		)
	end
__STORY_UNMARK__end

-- Remembers a squad spawned by a dialog/quest action so that _status can
-- freeze it and _reward/_cleanup can release it from the offline simulation.
local function register_dyn_squad(quest_id, squad)
	if not (quest_id and quest_id ~= "" and squad and squad.id) then
		return
	end
	local quest = QUESTS[quest_id]
	if not quest then return end
	local idx = (vget(quest.key_prefix .. "_dyn_squad_cnt", 0) or 0) + 1
	vset(quest.key_prefix .. "_dyn_squad_cnt", idx)
	vset(quest.key_prefix .. "_dyn_squad_" .. tostring(idx), squad.id)
end

-- Spawns a squad and pins it to a target smart (Warfare-safe).
local function spawn_task_squad(base_name, section, target_name)
	local base = get_smart(base_name)
	local target = get_smart(target_name) or base
	if not (base and target and SIMBOARD and SIMBOARD.create_squad) then
		printe("[__SCRIPT_NAME__] ! cannot spawn [%s] at [%s]",
			tostring(section), tostring(base_name))
		return nil
	end

	local ok, squad = pcall(function()
		return SIMBOARD:create_squad(base, section)
	end)
	if not ok or not squad then
		printe("[__SCRIPT_NAME__] ! spawn failed [%s]", tostring(section))
		return nil
	end

	mark_task_squad(squad)
	squad.stay_time = nil
	if sim_squad_warfare and sim_squad_warfare.set_target then
		pcall(sim_squad_warfare.set_target, squad, target.id)
	end
	if not squad.stay_time then
		squad.stay_time = game.get_game_time()
	end
	pcall(function() squad.force_online = true end)
	printf("[__SCRIPT_NAME__] squad [%s] id=%s -> [%s]",
		tostring(section), tostring(squad.id), tostring(target_name))
	return squad
end

-- Freezes a squad that has reached its destination.
local function freeze_squad(id)
	if not id or id == 0 then return end
	local squad = alife_object(id)
	if not squad then return end
	if squad.current_action == 1 then
		squad.stay_time = game.get_game_time()
		pcall(function() squad.force_online = true end)
		mark_task_squad(squad)
	end
end

-- Spawns every squad configured for one stage (idempotent).
local function spawn_stage_for(q, stage, data)
	if not (data and data.capture) then return end
	local spawn_key = stage_key(q, stage, "spawn")
	if vget(spawn_key, 0) == 1 then return end

	local capture = data.capture
	local smart = get_smart(capture.smart)
	if not smart then return end
	vset(spawn_key, 1)

	local enemy = spawn_task_squad(capture.smart, capture.enemy, capture.smart)
	if enemy then vset(stage_key(q, stage, "enemy"), enemy.id) end

	for i = 1, (capture.ally_count or 0) do
		local ally = spawn_task_squad(capture.smart, capture.ally, capture.smart)
		if ally then vset(stage_key(q, stage, "ally" .. i), ally.id) end
	end
end

-- Freezes all squads of the current stage.
local function freeze_stage_for(q, stage, data)
	if not (data and data.capture) then return end
	freeze_squad(vget(stage_key(q, stage, "enemy"), 0))
	for i = 1, (data.capture.ally_count or 0) do
		freeze_squad(vget(stage_key(q, stage, "ally" .. i), 0))
	end
end

-- Freezes every dynamically spawned squad of the quest (dialog SpawnSquad).
local function freeze_dyn_squads(q)
	if not q then return end
	local dyn_count = vget(q.key_prefix .. "_dyn_squad_cnt", 0) or 0
	for i = 1, dyn_count do
		freeze_squad(vget(q.key_prefix .. "_dyn_squad_" .. tostring(i), 0))
	end
end

-- A stage with capture data is cleared when its hostile squad is dead and
-- the point is owned by the army or has no defenders left.
local function stage_cleared(q, stage, data)
	if not (data and data.capture) then return false end
	local smart = get_smart(data.capture.smart)
	if not smart then return false end

	local enemy_id = vget(stage_key(q, stage, "enemy"), 0)
	if enemy_id == 0 then return false end
	if squad_alive(enemy_id) then return false end

	if smart.owning_faction == "army" then return true end
	if smart.defense_count ~= nil and smart.defense_count <= 0 then return true end
	return false
end

-- Returns true when the smart is owned by the requested faction.
local function is_smart_owned(smart_name, faction)
	local smart = get_smart(smart_name)
	if not smart then return false end
	return smart.owning_faction == faction
end

-- Adds money and reports the transfer once, using the vanilla news icon.
local function give_money(amount, actor)
	local obj = actor or db.actor
	amount = tonumber(amount) or 0
	if not (obj and amount > 0) then return end

	obj:give_money(amount)
	if news_manager and news_manager.relocate_money then
		news_manager.relocate_money(obj, "in", amount)
	end
end

-- Gives items to the actor one by one and reports the received stack once.
-- The section is resolved at compile time, so the news manager can show the
-- localized item name and icon instead of a raw alias.
local function give_item(section, count, actor)
	local obj = actor or db.actor
	if not (obj and section and section ~= "") then return end
	count = tonumber(count) or 1
	if count <= 0 then return end

	local given = 0
	for _ = 1, count do
		local ok, se_item = pcall(function()
			return alife_create_item(section, obj)
		end)
		if not (ok and se_item) then
			printe("[__SCRIPT_NAME__] ! cannot give item [%s]", tostring(section))
			break
		end
		given = given + 1
	end

	if given > 0 and news_manager and news_manager.relocate_item then
		news_manager.relocate_item(obj, "in", section, given)
	end
end

-- Removes the requested number of items directly from the actor inventory.
-- The transfer is reported exactly once at the end, so the engine does not
-- show a second "item lost" message.
local function take_item(section, count, actor)
	local obj = actor or db.actor
	if not (obj and section and section ~= "") then return end
	count = tonumber(count) or 1
	if count <= 0 then return end

	local removed = 0
	pcall(function()
		obj:iterate_inventory(function(owner, item)
			if removed >= count or not item then return end

			local item_section = nil
			local sec_ok, section_value = pcall(function() return item:section() end)
			if sec_ok then item_section = section_value end
			if item_section ~= section then return end

			local stack = 1
			local cnt_ok, cnt = pcall(function() return item:count() end)
			if cnt_ok and cnt and cnt > 0 then stack = cnt end

			local need = count - removed
			if stack > need then
				local cut_ok = pcall(function() item:set_count(stack - need) end)
				if cut_ok then removed = removed + need end
				return
			end

			local item_id = nil
			local id_ok, id_value = pcall(function() return item:id() end)
			if id_ok then item_id = id_value end
			if not item_id then return end

			local release_ok = pcall(function()
				alife_release(alife_object(item_id))
			end)
			if not release_ok then
				release_ok = pcall(function()
					alife():release(alife():object(item_id), true)
				end)
			end
			if release_ok then removed = removed + stack end
		end, nil)
	end)

	if removed > 0 and news_manager and news_manager.relocate_item then
		news_manager.relocate_item(obj, "out", section, removed)
	end
end

-- Gives a task from task_manager exactly once.
-- The quest giver comes from dialogs.who_is_npc(actor, npc); if the engine
-- passes a non-NPC speaker, the real (actor, npc) pair is used, and a name
-- configured in Quest.npc_id is resolved as the final fallback.
local function give_task(task_id, actor, npc)
	local tm = task_manager and task_manager.get_task_manager()
	if not tm then
		printe("[__SCRIPT_NAME__] ! task_manager is nil")
		return
	end
	if tm.task_info[task_id] then return end

	local giver = (dialogs and dialogs.who_is_npc and dialogs.who_is_npc(actor, npc)) or nil
	if not giver then
		local actor_id = db.actor and db.actor:id()
		if npc and npc.id and npc:id() ~= actor_id then
			giver = npc
		elseif actor and actor.id and actor:id() ~= actor_id then
			giver = actor
		end
	end

	local giver_id = nil
	if giver and giver.id then
		local id = giver:id()
		if id and id ~= 0 then
			giver_id = id
		end
	end

	if not giver_id then
		local quest = QUESTS[task_id]
		if quest and quest.npc ~= "" then
			giver_id = resolve_target(quest.npc)
			if not giver_id then
				local obj = resolve_alife_object(quest.npc)
				if obj and obj.id and obj.id ~= 0 then
					giver_id = obj.id
				end
			end
		end
	end

	tm:give_task(task_id, giver_id)
end

-- Completes a task through task_manager.
local function complete_task(task_id)
	local tm = task_manager and task_manager.get_task_manager()
	if tm and tm.task_info[task_id] then
		tm:set_task_completed(task_id)
	end
end

-- True when the player is close enough to the quest giver.
local function reached_giver(q, tsk)
	if not (q and db.actor) then return false end
	local giver = nil
	if tsk and tsk.task_giver_id and tsk.task_giver_id ~= 0 then
		giver = alife_object(tsk.task_giver_id)
	end
	if not giver and q.npc ~= "" then
		giver = resolve_alife_object(q.npc)
	end
	if not (giver and giver.position) then return false end
	local ok, distance = pcall(function()
		return db.actor:position():distance_to(giver.position)
	end)
	return ok and distance and distance < (q.return_distance or RETURN_DISTANCE)
end

-- Evaluates one serialized condition spec.
local function eval_condition(spec, actor)
	if not spec then return true end
	local kind = spec.kind
	if kind == "has_info" then
		return has_alife_info(spec.info)
	elseif kind == "dont_has_info" then
		return not has_alife_info(spec.info)
	elseif kind == "has_item" then
		return actor_item_count(spec.item, actor) >= (spec.count or 1)
	elseif kind == "has_money" then
		local obj = actor or db.actor
		if not obj then return false end
		local ok, balance = pcall(function() return obj:money() end)
		return ok and (balance or 0) >= (spec.amount or 0)
	elseif kind == "smart_owner" then
		return is_smart_owned(spec.smart, spec.faction)
	end
	return true
end

-- Evaluates a list of condition specs (AND).
local function eval_conditions(list, actor)
	if not list then return true end
	for _, spec in ipairs(list) do
		if not eval_condition(spec, actor) then return false end
	end
	return true
end

__NPC_ITEM_HELPERS____STORY_HELPERS____CLEAR_SMART_HELPERS__-- Executes a list of serialized action specs in order.
local function run_actions(actions, actor, npc, quest_id__STORY_RUN_ARGS__)
	if not actions then return end
	for _, spec in ipairs(actions) do
		local kind = spec.kind
		if kind == "give_info" then
			if db.actor then db.actor:give_info_portion(spec.info) end
		elseif kind == "remove_info" then
			if db.actor then db.actor:disable_info_portion(spec.info) end
		elseif kind == "give_money" then
			give_money(spec.amount, actor or db.actor)
		elseif kind == "take_money" then
			take_money(spec.amount, actor or db.actor)
		elseif kind == "give_item" then
			give_item(spec.item, spec.count, actor or db.actor)
		elseif kind == "remove_item" or kind == "take_item" then
			take_item(spec.item, spec.count, actor or db.actor)
		elseif kind == "spawn_squad" then
			local squad = spawn_task_squad(spec.smart, spec.squad, spec.smart)
			register_dyn_squad(quest_id, squad)
		elseif kind == "set_target" then
			spawn_task_squad(spec.smart, spec.squad, spec.smart)
		elseif kind == "give_task" then
			give_task(spec.task, actor, npc)
		elseif kind == "complete_task" then
			complete_task(spec.task)
__NPC_ITEM_ACTION_BRANCH____STORY_ACTION_BRANCHES____CLEAR_SMART_ACTION_BRANCH__		end
	end
end
"""


class LuaGenerator:
    """Собирает единый Lua-модуль квестов и диалогов проекта.

    Класс реализует только ``[4] RENDER``: он не пишет файлы и не патчит
    конфиги. Имя файла ``<mod>_quests.script`` и префикс pstor-ключей передаёт
    :class:`src.compiler.builder.ModBuilder`.
    """

    def __init__(self, db_client: Any | None = None) -> None:
        """Сохраняет необязательный клиент базы для будущих проверок ассетов.

        Args:
            db_client (Any | None):
                Клиент SQLite-базы. Генератор сейчас не обращается к нему, но
                сохраняет совместимость с :class:`src.core.validator`.
        """
        self.db_client = db_client

    # ------------------------------------------------------------------
    # Публичная точка входа
    # ------------------------------------------------------------------

    def generate_quests_script(
        self,
        project: "ModProject",
        *,
        script_name: str | None = None,
        mod_prefix: str | None = None,
    ) -> str:
        """Генерирует полный текст ``gamedata/scripts/<mod>_quests.script``.

        Args:
            project (ModProject):
                Проект с квестами и диалогами.
            script_name (str | None):
                Имя модуля для логов и шапки. По умолчанию ``"quests"``.
            mod_prefix (str | None):
                Префикс pstor-ключей. По умолчанию ``"quests"``.

        Returns:
            str: Готовый Lua 5.1-скрипт.

        Raises:
            TypeError: Если ``project.quests`` или ``project.dialogs`` не
                являются словарями.
        """
        quests = getattr(project, "quests", None)
        dialogs = getattr(project, "dialogs", None)
        if not isinstance(quests, dict) or not isinstance(dialogs, dict):
            raise TypeError("Проект должен содержать словари quests и dialogs.")

        # Карта отрядов нужна _action_spec, чтобы понять, удерживать ли
        # Story-отряд на точке спавна или он должен идти к target_smart.
        self._project_squads = getattr(project, "squads", None) or {}

        module_name = (script_name or DEFAULT_SCRIPT_NAME).strip() or DEFAULT_SCRIPT_NAME
        prefix = (mod_prefix or "quests").strip() or "quests"
        quest_ids = sorted(str(key) for key in quests)

        quest_data: dict[str, dict[str, Any]] = {}
        registrations: list[tuple[str, str, str]] = []
        blocks: list[str] = [self._build_header(module_name)]

        for quest_id in quest_ids:
            quest = quests[quest_id]
            try:
                data = self._build_quest_data(quest_id, quest, prefix)
                quest_data[quest_id] = data
            except Exception as exc:  # noqa: BLE001 - изоляция одного квеста
                logger.error(
                    "Квест '%s' пропущен: %s", quest_id, exc, exc_info=True
                )

        blocks.append(self._build_quests_table(quest_data))
        needs_story = self._project_uses_story(quests, dialogs)
        needs_npc_item = self._project_uses_npc_item(quests, dialogs)
        needs_clear_smart = self._project_uses_clear_smart(quests, dialogs)
        blocks.append(
            self._build_helpers(
                module_name,
                needs_story,
                needs_npc_item,
                needs_clear_smart,
            )
        )

        for quest_id, data in quest_data.items():
            quest = quests[quest_id]
            try:
                code, keys = self._build_quest_functions(
                    quest_id, quest, data, needs_story
                )
                blocks.append(code)
                registrations.extend(keys)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Квест '%s' пропущен при генерации функций: %s",
                    quest_id,
                    exc,
                    exc_info=True,
                )

        for dialog_key in sorted(str(key) for key in dialogs):
            dialog = dialogs[dialog_key]
            try:
                dialog_id = self._dialog_output_id(dialog)
                linked = self._linked_quest_id(dialog_id, dialog, quest_data)
                code, keys = self._build_dialog_functions(
                    dialog_id, dialog, linked, quest_data, needs_story
                )
                blocks.append(code)
                registrations.extend(keys)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Диалог '%s' пропущен при генерации функций: %s",
                    dialog_key,
                    exc,
                    exc_info=True,
                )

        blocks.append(
            self._build_registration(registrations, module_name)
        )
        blocks.append(
            f"-- End of auto-generated {module_name}.script"
        )
        script = "\n\n".join(
            block.rstrip() for block in blocks if block.strip()
        ) + "\n"
        return script.replace("__SCRIPT_NAME__", module_name)

    # ------------------------------------------------------------------
    # Служебные представления данных
    # ------------------------------------------------------------------

    @staticmethod
    def _dialog_output_id(dialog: "Dialog") -> str:
        """Возвращает канонический id диалога для имён Lua-функций.

        Args:
            dialog (Dialog): Модель диалога.

        Returns:
            str: ``dialog.dialog_id`` или ``dialog.id``.

        Raises:
            ValueError: Если идентификатор пуст или не является корректным
                Lua-идентификатором.
        """
        dialog_id = getattr(dialog, "dialog_id", None) or getattr(
            dialog, "id", None
        )
        if not isinstance(dialog_id, str) or not dialog_id.strip():
            raise ValueError(f"Некорректный ID диалога: {dialog_id!r}")
        dialog_id = dialog_id.strip()
        if not _is_lua_identifier(dialog_id):
            raise ValueError(
                f"ID диалога '{dialog_id}' не является допустимым "
                "Lua-идентификатором."
            )
        return dialog_id

    @staticmethod
    def _action_uses_story(action: Any) -> bool:
        """True, если действие относится к Story-отрядам.

        Args:
            action (Any): Действие модели.

        Returns:
            bool: ``SpawnSquad(mode="story")`` или ``RemoveSquad``.
        """
        if isinstance(action, RemoveSquad):
            return True
        return isinstance(action, SpawnSquad) and getattr(
            action, "mode", "warfare"
        ) == "story"

    @classmethod
    def _project_uses_story(
        cls, quests: dict[str, Any], dialogs: dict[str, Any]
    ) -> bool:
        """Проверяет, нужны ли проекту Story-хелперы.

        Учитываются действия квестов (init/start/reward/fail) и действия
        реплик диалогов, чтобы условные фрагменты не потерялись.

        Args:
            quests (dict[str, Any]): Карта квестов проекта.
            dialogs (dict[str, Any]): Карта диалогов проекта.

        Returns:
            bool: True, если найдено хотя бы одно Story-действие.
        """
        for quest in quests.values():
            action_lists = [
                getattr(quest, "on_init_actions", None) or [],
                getattr(quest, "on_complete_actions", None) or [],
                getattr(quest, "on_fail_actions", None) or [],
            ]
            for stage in (getattr(quest, "stages", None) or {}).values():
                action_lists.append(getattr(stage, "on_start_actions", None) or [])
            for actions in action_lists:
                if any(cls._action_uses_story(action) for action in actions):
                    return True
        for dialog in dialogs.values():
            for phrase in (getattr(dialog, "phrases", None) or {}).values():
                actions = getattr(phrase, "actions", None) or []
                if any(cls._action_uses_story(action) for action in actions):
                    return True
        return False

    @staticmethod
    def _action_uses_npc_item(action: Any) -> bool:
        """True, если действие — :class:`SpawnNpcItem`.

        Args:
            action (Any): Действие модели.

        Returns:
            bool: Действие спавнит предмет в инвентарь NPC.
        """
        return isinstance(action, SpawnNpcItem)

    @classmethod
    def _project_uses_npc_item(
        cls, quests: dict[str, Any], dialogs: dict[str, Any]
    ) -> bool:
        """Проверяет, нужен ли проекту хелпер ``spawn_npc_item``.

        Учитываются действия квестов (init/start/reward/fail) и действия
        реплик диалогов. Если ``SpawnNpcItem`` не используется, хелпер не
        вставляется и вывод остаётся байт-идентичным прежнему.

        Args:
            quests (dict[str, Any]): Карта квестов проекта.
            dialogs (dict[str, Any]): Карта диалогов проекта.

        Returns:
            bool: True, если найдено хотя бы одно ``SpawnNpcItem``.
        """
        for quest in quests.values():
            action_lists = [
                getattr(quest, "on_init_actions", None) or [],
                getattr(quest, "on_complete_actions", None) or [],
                getattr(quest, "on_fail_actions", None) or [],
            ]
            for stage in (getattr(quest, "stages", None) or {}).values():
                action_lists.append(getattr(stage, "on_start_actions", None) or [])
            for actions in action_lists:
                if any(cls._action_uses_npc_item(action) for action in actions):
                    return True
        for dialog in dialogs.values():
            for phrase in (getattr(dialog, "phrases", None) or {}).values():
                actions = getattr(phrase, "actions", None) or []
                if any(cls._action_uses_npc_item(action) for action in actions):
                    return True
        return False

    @staticmethod
    def _action_uses_clear_smart(action: Any) -> bool:
        """True, если действие — :class:`ClearSmart`.

        Args:
            action (Any): Действие модели.

        Returns:
            bool: Действие очищает смарт перед спавном.
        """
        return isinstance(action, ClearSmart)

    @classmethod
    def _project_uses_clear_smart(
        cls, quests: dict[str, Any], dialogs: dict[str, Any]
    ) -> bool:
        """Проверяет, нужен ли проекту Lua-хелпер ``clear_smart``.

        Учитываются действия квестов (init/start/reward/fail) и действия
        реплик диалогов. Если ``ClearSmart`` не используется, хелпер и ветка
        не вставляются, поэтому вывод остаётся байт-идентичным прежнему.

        Args:
            quests (dict[str, Any]): Карта квестов проекта.
            dialogs (dict[str, Any]): Карта диалогов проекта.

        Returns:
            bool: True, если найдено хотя бы одно ``ClearSmart``.
        """
        for quest in quests.values():
            action_lists = [
                getattr(quest, "on_init_actions", None) or [],
                getattr(quest, "on_complete_actions", None) or [],
                getattr(quest, "on_fail_actions", None) or [],
            ]
            for stage in (getattr(quest, "stages", None) or {}).values():
                action_lists.append(getattr(stage, "on_start_actions", None) or [])
            for actions in action_lists:
                if any(
                    cls._action_uses_clear_smart(action) for action in actions
                ):
                    return True
        for dialog in dialogs.values():
            for phrase in (getattr(dialog, "phrases", None) or {}).values():
                actions = getattr(phrase, "actions", None) or []
                if any(
                    cls._action_uses_clear_smart(action) for action in actions
                ):
                    return True
        return False

    @staticmethod
    def _linked_quest_id(
        dialog_id: str,
        dialog: "Dialog",
        quest_data: dict[str, dict[str, Any]],
    ) -> str | None:
        """Находит квест, связанный с диалогом.

        Сначала используется явное поле ``Dialog.task_id``, затем обратный
        поиск по ``Quest.dialog_id``/``Quest.dialog_ids``.

        Args:
            dialog_id (str): Канонический id диалога.
            dialog (Dialog): Модель диалога.
            quest_data (dict[str, dict[str, Any]]):
                Уже сериализованные данные квестов.

        Returns:
            str | None: ID квеста или ``None``, если связь не задана.
        """
        task_id = getattr(dialog, "task_id", None)
        if isinstance(task_id, str) and task_id in quest_data:
            return task_id
        for quest_id, data in quest_data.items():
            if data.get("dialog") == dialog_id:
                return quest_id
            for linked in data.get("dialog_ids", []):
                if linked == dialog_id:
                    return quest_id
        return None

    def _resolve_item_section(self, item_alias: str) -> str:
        """Приводит алиас БД к секции предмета, не ломая прямой section.

        Если клиент базы не передан, не содержит ``find_item_by_alias`` или
        алиас не найден, возвращается исходная строка. Это позволяет писать
        как ``itm_pda_common``, так и алиасы из ``data/anomaly_db.sqlite``.

        Args:
            item_alias (str): Секция или алиас предмета.

        Returns:
            str: Секция предмета для игрового Lua.
        """
        value = str(item_alias or "").strip()
        if not value:
            return ""
        finder = getattr(self.db_client, "find_item_by_alias", None)
        if not callable(finder):
            return value
        try:
            row = finder(value)
        except Exception as exc:  # noqa: BLE001 - база не должна ронять сборку
            logger.warning(
                "Не удалось разрешить алиас предмета %r через БД: %s",
                value,
                exc,
            )
            return value
        if isinstance(row, dict):
            section = row.get("id") or row.get("section")
            if isinstance(section, str) and section.strip():
                return section.strip()
        logger.warning(
            "Алиас/секция предмета %r не найдена в БД; используется как есть.",
            value,
        )
        return value

    def _resolve_squad_section(self, squad_id: str | None) -> str:
        """Приводит алиас отряда к секции, сохраняя прямые section/story id.

        Args:
            squad_id (str | None): Секция, story id или алиас отряда.

        Returns:
            str: Секция/ID отряда для игрового Lua либо пустая строка.
        """
        value = str(squad_id or "").strip()
        if not value:
            return ""
        finder = getattr(self.db_client, "find_squad_by_alias", None)
        if not callable(finder):
            return value
        try:
            row = finder(value)
        except Exception as exc:  # noqa: BLE001 - база не должна ронять сборку
            logger.warning(
                "Не удалось разрешить алиас отряда %r через БД: %s",
                value,
                exc,
            )
            return value
        if isinstance(row, dict):
            section = row.get("id") or row.get("section")
            if isinstance(section, str) and section.strip():
                return section.strip()
        logger.warning(
            "Алиас/секция отряда %r не найдена в БД; используется как есть.",
            value,
        )
        return value

    def _find_squad_entry(
        self,
        alias: str | None,
        squads: dict[str, Any] | None = None,
    ) -> Any | None:
        """Ищет ``CustomSquad`` проекта по id, story_id или ключу карты.

        Args:
            alias (str | None): Алиас/секция/story id отряда.
            squads (dict[str, Any] | None): Карта отрядов проекта. Если не
                задана, используется карта текущей генерации.

        Returns:
            Any | None: Найденный ``CustomSquad`` либо ``None``.
        """
        if not alias:
            return None
        source = (
            squads
            if squads is not None
            else getattr(self, "_project_squads", None)
        )
        if not isinstance(source, dict):
            return None
        value = str(alias).strip()
        if not value:
            return None
        for key, squad in source.items():
            if value in (
                str(key),
                str(getattr(squad, "id", "") or ""),
                str(getattr(squad, "story_id", "") or ""),
            ):
                return squad
        return None

    def _condition_spec(self, condition: "Condition") -> dict[str, Any]:
        """Преобразует Pydantic-условие в словарь для Lua.

        Args:
            condition (Condition): Условие модели.

        Returns:
            dict[str, Any]: Словарь ``{"kind": ..., ...}``.

        Raises:
            TypeError: Если тип условия неизвестен.
        """
        if isinstance(condition, HasInfo):
            return {"kind": "has_info", "info": condition.info}
        if isinstance(condition, DontHasInfo):
            return {"kind": "dont_has_info", "info": condition.info}
        if isinstance(condition, HasItem):
            return {
                "kind": "has_item",
                "item": self._resolve_item_section(condition.item_alias),
                "count": condition.count,
            }
        if isinstance(condition, HasMoney):
            return {"kind": "has_money", "amount": condition.amount}
        if isinstance(condition, SmartOwner):
            return {
                "kind": "smart_owner",
                "smart": condition.smart_alias,
                "faction": condition.faction,
            }
        raise TypeError(f"Неизвестный тип условия: {type(condition).__name__}")

    def _action_spec(
        self,
        action: Any,
        squads: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Преобразует Pydantic-действие в словарь для Lua.

        Args:
            action (Any): Действие модели.
            squads (dict[str, Any] | None): Карта ``CustomSquad`` проекта.
                Если не задана, используется карта, сохранённая
                :meth:`generate_quests_script`.

        Returns:
            dict[str, Any]: Словарь ``{"kind": ..., ...}``.

        Raises:
            TypeError: Если тип действия неизвестен.
        """
        if isinstance(action, GiveInfo):
            return {"kind": "give_info", "info": action.info}
        if isinstance(action, RemoveInfo):
            return {"kind": "remove_info", "info": action.info}
        if isinstance(action, SpawnSquad):
            if action.mode == "story":
                squad = self._find_squad_entry(action.squad_alias, squads)
                target_smart = str(
                    getattr(squad, "target_smart", None) or ""
                ).strip()
                spawn_smart = str(action.smart_alias or "").strip()
                # Отряд нужно удерживать на точке спавна, только если у него
                # нет маршрута в LTX или маршрут совпадает с точкой спавна.
                # Иначе Story-отряд обязан дойти до target_smart маршем.
                hold = not target_smart or target_smart == spawn_smart
                return {
                    "kind": "spawn_story_squad",
                    "squad": self._resolve_squad_section(action.squad_alias),
                    "smart": action.smart_alias,
                    "hold": hold,
                }
            return {
                "kind": "spawn_squad",
                "squad": action.squad_alias,
                "smart": action.smart_alias,
            }
        if isinstance(action, RemoveSquad):
            return {
                "kind": "remove_squad",
                "squad": action.squad_alias,
            }
        if isinstance(action, SetTarget):
            return {
                "kind": "set_target",
                "squad": action.squad_alias,
                "smart": action.smart_alias,
            }
        if isinstance(action, ClearSmart):
            return {
                "kind": "clear_smart",
                "smart": action.smart_alias,
                "faction": action.faction or "",
                "keep_story_ids": list(action.keep_story_ids),
            }
        if isinstance(action, SpawnNpcItem):
            return {
                "kind": "spawn_npc_item",
                "item": self._resolve_item_section(action.item_alias),
                "target": action.target_alias,
                "count": action.count,
            }
        if isinstance(action, GiveItem):
            return {
                "kind": "give_item",
                "item": self._resolve_item_section(action.item_alias),
                "count": action.count,
            }
        if isinstance(action, RemoveItem):
            return {
                "kind": "remove_item",
                "item": self._resolve_item_section(action.item_alias),
                "count": action.count,
            }
        if isinstance(action, TakeItem):
            return {
                "kind": "take_item",
                "item": self._resolve_item_section(action.item_alias),
                "count": action.count,
            }
        if isinstance(action, GiveMoney):
            return {"kind": "give_money", "amount": action.amount}
        if isinstance(action, TakeMoney):
            return {"kind": "take_money", "amount": action.amount}
        if isinstance(action, GiveTask):
            return {"kind": "give_task", "task": action.task_id}
        if isinstance(action, CompleteTask):
            return {"kind": "complete_task", "task": action.task_id}
        raise TypeError(f"Неизвестный тип действия: {type(action).__name__}")

    def _build_quest_data(
        self, quest_id: str, quest: "Quest", mod_prefix: str
    ) -> dict[str, Any]:
        """Сериализует модель квеста в структуру для ``local QUESTS``.

        Args:
            quest_id (str): ID квеста (ключ карты и секция LTX).
            quest (Quest): Модель квеста.
            mod_prefix (str): Префикс pstor-ключей.

        Returns:
            dict[str, Any]: Данные, пригодные для :meth:`_to_lua`.

        Raises:
            ValueError: Если ID квеста не является Lua-идентификатором.
        """
        if not _is_lua_identifier(quest_id):
            raise ValueError(
                f"ID квеста '{quest_id}' не является допустимым "
                "Lua-идентификатором."
            )

        stages: dict[int, dict[str, Any]] = {}
        transfer_conditions = getattr(quest, "transfer_conditions", {}) or {}
        for stage_id, stage in sorted(quest.stages.items()):
            rules = transfer_conditions.get(stage_id, {}) or {}
            capture = None
            if stage.warfare_capture is not None:
                capture = {
                    "smart": stage.warfare_capture.smart_alias,
                    "enemy": stage.warfare_capture.enemy_squad_alias,
                    "ally": stage.warfare_capture.ally_squad_alias or "",
                    "ally_count": stage.warfare_capture.ally_count,
                }
            # GiveItem из on_start_actions выдаётся идемпотентно: _status
            # повторяет выдачу каждый тик, если предмет потерян. Остальные
            # действия по-прежнему выполняются один раз (ключ "started").
            # SpawnNpcItem вынесен отдельно: если командир отряда ещё не
            # инициализирован, _status повторяет попытку на следующих тиках.
            start_actions: list[dict[str, Any]] = []
            item_actions: list[dict[str, Any]] = []
            npc_item_actions: list[dict[str, Any]] = []
            for action in stage.on_start_actions:
                spec = self._action_spec(action)
                if isinstance(action, GiveItem):
                    item_actions.append(spec)
                elif isinstance(action, SpawnNpcItem):
                    npc_item_actions.append(spec)
                else:
                    start_actions.append(spec)
            # target_variants / descr_variants (only serialized if non-empty)
            target_variants = []
            for variant in getattr(stage, "target_variants", []) or []:
                target_variants.append({
                    "when": [self._condition_spec(c) for c in variant.when],
                    "value": variant.value,
                })
            descr_variants = []
            for idx, variant in enumerate(getattr(stage, "descr_variants", []) or []):
                descr_variants.append({
                    "when": [self._condition_spec(c) for c in variant.when],
                    "key": f"{quest_id}_stage_{stage_id}_descr_v{idx + 1}",
                })

            stage_data: dict[str, Any] = {
                "target": stage.target_alias or "",
                "target_squad": self._resolve_squad_section(
                    stage.target_squad_id
                ),
                "descr": f"{quest_id}_stage_{stage_id}_descr",
                "msg": f"{quest_id}_stage_{stage_id}_msg",
                "capture": capture,
                "start_actions": start_actions,
                "item_actions": item_actions,
                "complete": [
                    self._condition_spec(condition)
                    for condition in (rules.get("complete") or [])
                ],
                "fail": [
                    self._condition_spec(condition)
                    for condition in (rules.get("fail") or [])
                ],
            }
            if target_variants:
                stage_data["target_variants"] = target_variants
            if descr_variants:
                stage_data["descr_variants"] = descr_variants
            if npc_item_actions:
                stage_data["npc_item_actions"] = npc_item_actions
            stages[stage_id] = stage_data

        # Автоматическая очистка этапных GiveInfo. Поршни, выданные на старте
        # этапа (например, "*_ready" для диалога сдачи), обязаны сниматься
        # при провале/отмене квеста, иначе после повторного взятия они
        # открывают диалог сдачи до фактического прохождения этапов.
        cleanup_infos: list[str] = []
        for info in getattr(quest, "cleanup_infos", []) or []:
            if info and info not in cleanup_infos:
                cleanup_infos.append(info)
        complete_info = quest.complete_info or ""
        done_info = quest.done_info or ""
        for stage in quest.stages.values():
            for action in stage.on_start_actions:
                if not isinstance(action, GiveInfo):
                    continue
                info = action.info or ""
                if (
                    info
                    and info != complete_info
                    and info != done_info
                    and info not in cleanup_infos
                ):
                    cleanup_infos.append(info)

        return {
            "id": quest_id,
            "key_prefix": f"{mod_prefix}_{quest_id}",
            "npc": quest.npc_id or quest.giver_npc_id or "",
            "npc_location": quest.npc_location or "",
            "dialog": quest.dialog_id or "",
            "dialog_ids": list(quest.dialog_ids),
            "title": f"{quest_id}_title",
            "descr": f"{quest_id}_descr",
            "msg_reward": f"{quest_id}_msg_reward",
            "msg_fail": f"{quest_id}_msg_fail",
            "msg_start": f"{quest_id}_msg_start",
            "taken_info": quest.taken_info or "",
            "complete_info": quest.complete_info or "",
            "cleanup_infos": cleanup_infos,
            "available_info": quest.available_info or "",
            "done_info": quest.done_info or "",
            "requires_faction": quest.requires_faction or "",
            "requires_warfare": bool(quest.requires_warfare),
            "storyline": bool(quest.is_storyline),
            "icon": quest.icon or DEFAULT_ICON,
            "prior": quest.prior if quest.prior is not None else DEFAULT_PRIOR,
            "money": quest.reward_money or 0,
            "item": self._resolve_item_section(quest.reward_item_alias or ""),
            "item_count": quest.reward_item_count,
            "return_stage": (
                quest.return_to_giver_stage
                if quest.return_to_giver_stage is not None
                else -1
            ),
            "return_distance": quest.return_distance,
            "last_stage": max(quest.stages) if quest.stages else 0,
            "world": any(
                stage.warfare_capture is not None
                for stage in quest.stages.values()
            ),
            "stages": stages,
            "init_actions": [
                self._action_spec(action) for action in quest.on_init_actions
            ],
            "complete_actions": [
                self._action_spec(action)
                for action in quest.on_complete_actions
            ],
            "fail_actions": [
                self._action_spec(action) for action in quest.on_fail_actions
            ],
        }

    # ------------------------------------------------------------------
    # Генерация блоков
    # ------------------------------------------------------------------

    @staticmethod
    def _build_header(script_name: str) -> str:
        """Формирует шапку-комментарий Lua-модуля.

        Args:
            script_name (str): Имя модуля для комментария.

        Returns:
            str: Текст комментария ``--[[ ... ]]``.
        """
        return f"""\
--[[
	{script_name}.script
	---------------------------------------------------------------------------
	Automatically generated by the quest-framework compiler.
	Lua 5.1 / S.T.A.L.K.E.R. Anomaly.

	All engine functions are registered at module level with flat keys in
	task_functor / task_status_functor / xr_effects / dialogs.
	Dialogs are bound declaratively through character_desc_<level>.xml.
]]"""

    def _build_quests_table(self, quest_data: dict[str, dict[str, Any]]) -> str:
        """Формирует статическую таблицу ``local QUESTS``.

        Args:
            quest_data (dict[str, dict[str, Any]]):
                Сериализованные данные квестов.

        Returns:
            str: Объявление ``local QUESTS = { ... }``.
        """
        return "local QUESTS = " + self._to_lua(quest_data, indent=0)

    def _build_helpers(
        self,
        script_name: str,
        needs_story: bool,
        needs_npc_item: bool = False,
        needs_clear_smart: bool = False,
    ) -> str:
        """Подставляет имя модуля и константы в шаблон общих хелперов.

        Story-, NPC-item- и clear-smart-фрагменты вставляются только при
        соответствующих флагах; для проектов без них шаблон остаётся
        байт-идентичным прежнему.

        Args:
            script_name (str): Имя модуля для логов.
            needs_story (bool): Проект использует хотя бы одно Story-действие
                (``SpawnSquad(mode="story")`` или ``RemoveSquad``).
            needs_npc_item (bool): Проект использует ``SpawnNpcItem``.
            needs_clear_smart (bool): Проект использует ``ClearSmart``.

        Returns:
            str: Lua-код generic-хелперов.
        """
        npc_item_helpers = ""
        npc_item_branch = ""
        story_helpers = ""
        story_unmark = ""
        story_branches = ""
        story_run_args = ""
        clear_smart_helpers = ""
        clear_smart_branch = ""
        if needs_npc_item:
            npc_item_helpers = (
                "\n"
                + r"""-- Spawns an item into an NPC inventory or a squad commander
-- for later looting; no news_manager notifications are emitted.
-- Returns true only when the target server object (or squad commander)
-- exists and every alife_create_item call produced an item.
local function spawn_npc_item(section, target_name, count)
	if not (section and section ~= "" and target_name and target_name ~= "") then
		return false
	end
	local obj = resolve_alife_object(target_name)
	if not obj and get_story_squad then
		local squad_ok, squad = pcall(function()
			return get_story_squad(target_name)
		end)
		if squad_ok and squad then obj = squad end
	end
	if not obj then
		printe("[__SCRIPT_NAME__] ! cannot resolve NPC/squad [%s] for item [%s]",
			tostring(target_name), tostring(section))
		return false
	end
	if obj.commander_id then
		local cmd_id = obj:commander_id()
		local commander = nil
		if cmd_id and cmd_id ~= 0 then
			commander = alife_object(cmd_id)
		end
		if not commander then
			printe("[__SCRIPT_NAME__] ! commander of [%s] is not ready for item [%s]",
				tostring(target_name), tostring(section))
			return false
		end
		obj = commander
	end
	count = tonumber(count) or 1
	for _ = 1, count do
		local ok, se_item = pcall(function()
			return alife_create_item(section, obj)
		end)
		if not (ok and se_item) then
			printe("[__SCRIPT_NAME__] ! cannot create item [%s] for [%s]",
				tostring(section), tostring(target_name))
			return false
		end
	end
	return true
end"""
                + "\n\n"
            )
            npc_item_branch = (
                '\t\telseif kind == "spawn_npc_item" then\n'
                "\t\t\tspawn_npc_item(spec.item, spec.target, spec.count)\n"
            )
        if needs_story:
            story_helpers = (
                "\n"
                + r"""-- Story squads: separate namespace, no sim_squad_warfare calls.
local function register_story_squad(quest_id, squad)
	if not (quest_id and quest_id ~= "" and squad and squad.id) then
		return
	end
	local quest = QUESTS[quest_id]
	if not quest then return end
	local idx = (vget(quest.key_prefix .. "_story_squad_cnt", 0) or 0) + 1
	vset(quest.key_prefix .. "_story_squad_cnt", idx)
	vset(quest.key_prefix .. "_story_squad_" .. tostring(idx), squad.id)
end

-- Spawns a story squad. When hold is true the squad is pinned to the spawn
-- smart; otherwise its LTX target_smart drives the march.
local function spawn_story_squad(base_name, section, quest_id, once_key, hold)
	if once_key and vget(once_key, 0) == 1 then
		return
	end
	local base = get_smart(base_name)
	if not (base and SIMBOARD and SIMBOARD.create_squad) then
		printe("[__SCRIPT_NAME__] ! cannot spawn story squad [%s] at [%s]",
			tostring(section), tostring(base_name))
		return nil
	end

	local ok, squad = pcall(function()
		return SIMBOARD:create_squad(base, section)
	end)
	if not ok or not squad then
		printe("[__SCRIPT_NAME__] ! story spawn failed [%s]", tostring(section))
		return nil
	end

	mark_task_squad(squad)
	register_story_squad(quest_id, squad)
	-- force_online keeps A-Life from re-assigning a freshly created story
	-- squad to another smart while it is still offline. stay_time is set only
	-- for squads that must hold the spawn point, so marching squads still move.
	if hold then
		squad.stay_time = game.get_game_time()
	end
	pcall(function() squad.force_online = true end)
	if once_key then
		vset(once_key, 1)
	end
	printf("[__SCRIPT_NAME__] story squad [%s] id=%s spawned at [%s]",
		tostring(section), tostring(squad.id), tostring(base_name))
	return squad
end

-- Removes a story squad by story id/section; missing squad is a safe no-op.
local function remove_story_squad(alias_or_section)
	if not alias_or_section or alias_or_section == "" then return end
	local squad = nil
	if get_story_squad then
		local ok, found = pcall(function()
			return get_story_squad(alias_or_section)
		end)
		if ok and found then squad = found end
	end
	if not squad then
		squad = resolve_alife_object(alias_or_section)
	end
	if squad and SIMBOARD and SIMBOARD.remove_squad then
		pcall(SIMBOARD.remove_squad, SIMBOARD, squad)
	end
end"""
                + "\n\n"
            )
            story_unmark = (
                "\t-- Story squads: separate namespace so freeze_dyn_squads "
                "never touches them.\n"
                "\tlocal story_cnt = vget(q.key_prefix .. "
                '"_story_squad_cnt", 0) or 0\n'
                "\tfor i = 1, story_cnt do\n"
                "\t\tunmark_task_squad(\n"
                '\t\t\tvget(q.key_prefix .. "_story_squad_" .. '
                'tostring(i), 0)\n'
                "\t\t)\n"
                "\tend\n"
                '\tvset(q.key_prefix .. "_story_squad_cnt", 0)\n'
                "\t-- Reset init spawn flag so a re-taken cancelled quest "
                "can spawn again.\n"
                '\tvset(q.key_prefix .. "_init_spawn", 0)\n'
            )
            story_branches = (
                '\t\telseif kind == "spawn_story_squad" then\n'
                "\t\t\tlocal quest = QUESTS[quest_id]\n"
                "\t\t\tif quest then\n"
                "\t\t\t\tlocal once_key\n"
                "\t\t\t\tif stage_idx and stage_idx >= 0 then\n"
                '\t\t\t\t\tonce_key = stage_key(quest, stage_idx, '
                '"story_spawn")\n'
                "\t\t\t\telse\n"
                '\t\t\t\t\tonce_key = quest.key_prefix .. '
                '"_init_spawn"\n'
                "\t\t\t\tend\n"
                "\t\t\t\tspawn_story_squad(spec.smart, spec.squad, "
                "quest_id, once_key, spec.hold)\n"
                "\t\t\tend\n"
                '\t\telseif kind == "remove_squad" then\n'
                "\t\t\tremove_story_squad(spec.squad)\n"
            )
            story_run_args = ", stage_idx"

        if needs_clear_smart:
            clear_smart_helpers = (
                "\n"
                + r"""-- Clears vanilla squads from a smart before a quest squad spawns
-- there. Skips the actor, companions, offline-combat task squads, story
-- squads and the explicitly allowed keep_story_ids list.
local function clear_smart_is_kept(squad, keep_story_ids)
	if not (squad and squad.id and keep_story_ids) then return false end
	for _, keep in ipairs(keep_story_ids) do
		if keep and keep ~= "" then
			if squad.story_id == keep then return true end
			if tostring(squad.id) == tostring(keep) then return true end
			if get_object_story_id then
				local ok, story_id = pcall(function()
					return get_object_story_id(squad.id)
				end)
				if ok and story_id and tostring(story_id) == tostring(keep) then
					return true
				end
			end
		end
	end
	return false
end

-- True when the squad is bound to the requested smart. After loading a save,
-- offline squads often keep the link in assigned_target_id/current_target_id
-- instead of smart_id/m_smart_terrain_id.
local function clear_smart_bound_to(squad, smart_id)
	if not (squad and smart_id) then return false end
	return squad.smart_id == smart_id
		or squad.m_smart_terrain_id == smart_id
		or squad.assigned_target_id == smart_id
		or squad.current_target_id == smart_id
end

local function clear_smart(smart_name, faction, keep_story_ids)
	local smart = get_smart(smart_name)
	if not smart then
		printe("[__SCRIPT_NAME__] ! clear_smart: smart [%s] not found",
			tostring(smart_name))
		return 0
	end
	local keep = keep_story_ids or {}
	local actor_id = db.actor and db.actor:id() or nil
	local seen = {}
	local candidates = {}

	local function consider(squad)
		if not (squad and squad.id) then return end
		if seen[squad.id] then return end
		seen[squad.id] = true
		if actor_id and squad.id == actor_id then return end
		if squad.is_companion then return end
		if clear_smart_is_kept(squad, keep) then return end
		local task_squads = sim_offline_combat
			and sim_offline_combat.task_squads
		if task_squads and task_squads[squad.id] then return end
		if get_object_story_id then
			local ok, story_id = pcall(function()
				return get_object_story_id(squad.id)
			end)
			if ok and story_id and story_id ~= 0 and story_id ~= "" then
				return
			end
		end
		if faction and faction ~= "" then
			local ok, community = pcall(function()
				return squad:get_squad_community()
			end)
			if not ok or community ~= faction then return end
		end
		candidates[#candidates + 1] = squad
	end

	pcall(function()
		if smart.squads then
			for _, squad in pairs(smart.squads) do
				consider(squad)
			end
		end
		if SIMBOARD and SIMBOARD.squads then
			for _, squad in pairs(SIMBOARD.squads) do
				if clear_smart_bound_to(squad, smart.id) then
					consider(squad)
				end
			end
		end
	end)

	local removed = 0
	for _, squad in ipairs(candidates) do
		if squad and squad.id then
			local live = alife_object(squad.id) ~= nil
			local release_ok = true
			if live then
				local task_squads = sim_offline_combat
					and sim_offline_combat.task_squads
				if task_squads then task_squads[squad.id] = nil end
				release_ok = pcall(function()
					SIMBOARD:remove_squad(squad)
				end)
				if release_ok then removed = removed + 1 end
			end
			-- remove_squad may leave a stale reference in smart.squads
			-- (and an already released squad has no server object at all).
			-- Drop every candidate reference immediately so the population
			-- slot is free before the story squad is created by next action.
			if release_ok and smart.squads then
				local stale = {}
				for key, value in pairs(smart.squads) do
					if key == squad.id or value == squad then
						stale[#stale + 1] = key
					end
				end
				for _, key in ipairs(stale) do
					smart.squads[key] = nil
				end
			end
		end
	end
	printf("[__SCRIPT_NAME__] clear_smart [%s] faction=[%s] keep=%s removed=%s",
		tostring(smart_name), tostring(faction or ""),
		tostring(#keep), tostring(removed))
	return removed
end"""
                + "\n\n"
            )
            clear_smart_branch = (
                '\t\telseif kind == "clear_smart" then\n'
                "\t\t\tclear_smart(spec.smart, spec.faction, "
                "spec.keep_story_ids)\n"
            )

        return (
            _HELPERS_TEMPLATE.replace("__SCRIPT_NAME__", script_name)
            .replace("__PDA_SOUND__", DEFAULT_PDA_SOUND)
            .replace("__STATUS_THROTTLE__", str(DEFAULT_STATUS_THROTTLE_MS))
            .replace("__RETURN_DISTANCE__", str(DEFAULT_RETURN_DISTANCE))
            .replace("__NPC_ITEM_HELPERS__", npc_item_helpers)
            .replace("__NPC_ITEM_ACTION_BRANCH__", npc_item_branch)
            .replace("__STORY_UNMARK__", story_unmark)
            .replace("__STORY_HELPERS__", story_helpers)
            .replace("__STORY_ACTION_BRANCHES__", story_branches)
            .replace("__STORY_RUN_ARGS__", story_run_args)
            .replace("__CLEAR_SMART_HELPERS__", clear_smart_helpers)
            .replace(
                "__CLEAR_SMART_ACTION_BRANCH__", clear_smart_branch
            )
            .strip()
        )

    def _build_quest_functions(
        self,
        quest_id: str,
        quest: "Quest",
        data: dict[str, Any],
        needs_story: bool = False,
    ) -> tuple[str, list[tuple[str, str, str]]]:
        """Генерирует плоские функции одного квеста.

        Функции ``_target``/``_descr``/``_status`` регистрируются в
        ``task_functor``/``task_status_functor``; ``_start``/``_reward``/
        ``_cleanup`` — в ``xr_effects``; ``_accept``/``_turn_in`` — в
        ``dialogs`` (``standart_of_auto.md``, 2.3).

        Args:
            quest_id (str): ID квеста.
            quest (Quest): Модель квеста.
            data (dict[str, Any]): Сериализованные данные квеста.
            needs_story (bool): Проект использует Story-действия; добавляет
                аргумент ``stage_idx`` в вызовы ``run_actions``.

        Returns:
            tuple[str, list[tuple[str, str, str]]]:
                Lua-код и список регистраций ``(table, key, function)``.
        """
        q = self._lua_string(quest_id)
        keys: list[tuple[str, str, str]] = []
        stage_arg = ", stage" if needs_story else ""
        extra_arg = ", -1" if needs_story else ""
        story_reset = (
            '\t\tvset(stage_key(quest, stage, "story_spawn"), 0)\n'
            if needs_story
            else ""
        )

        # SpawnNpcItem из on_start_actions повторяется, пока командир отряда
        # не будет доступен: результат вызова фиксируется отдельными
        # pstor-ключами, а не общим "started".
        npc_item_reset = ""
        npc_item_status = ""
        if any(
            stage_data.get("npc_item_actions")
            for stage_data in data["stages"].values()
        ):
            npc_item_reset = (
                '\t\tvset(stage_key(quest, stage, "npc_item_done"), 0)\n'
                "\t\tfor i = 1, #(stage_data.npc_item_actions or {}) do\n"
                '\t\t\tvset(stage_key(quest, stage, '
                '"npc_item_done_" .. tostring(i)), 0)\n'
                "\t\tend\n"
            )
            npc_item_status = (
                "\t-- NPC items from on_start_actions are retried on later\n"
                "\t-- status ticks until the squad commander is available.\n"
                '\tif vget(stage_key(quest, stage, "npc_item_done"), 0) == 0 then\n'
                "\t\tlocal npc_items_done = true\n"
                "\t\tfor idx, item_spec in ipairs("
                "stage_data.npc_item_actions or {}) do\n"
                "\t\t\tlocal item_key = stage_key(\n"
                '\t\t\t\tquest, stage, "npc_item_done_" .. tostring(idx)\n'
                "\t\t\t)\n"
                "\t\t\tif vget(item_key, 0) == 0 then\n"
                "\t\t\t\tif spawn_npc_item(item_spec.item, "
                "item_spec.target, item_spec.count) then\n"
                "\t\t\t\t\tvset(item_key, 1)\n"
                "\t\t\t\telse\n"
                "\t\t\t\t\tnpc_items_done = false\n"
                "\t\t\t\tend\n"
                "\t\t\tend\n"
                "\t\tend\n"
                "\t\tif npc_items_done then\n"
                '\t\t\tvset(stage_key(quest, stage, "npc_item_done"), 1)\n'
                "\t\tend\n"
                "\tend\n"
            )

        # Build target function with optional target_variants
        target_variants_code = ""
        if data["stages"]:
            # Check if any stage has target_variants
            has_target_variants = any(
                stage_data.get("target_variants")
                for stage_data in data["stages"].values()
            )
            if has_target_variants:
                target_variants_code = """\t-- Check target_variants for current stage
\tlocal variants = (stage_data and stage_data.target_variants) or {}
\tfor _, var in ipairs(variants) do
\t\tif eval_conditions(var.when, db.actor) then
\t\t\tlocal target_id = resolve_target(var.value)
\t\t\tif target_id then return target_id end
\t\t\tlocal target_obj = resolve_alife_object(var.value)
\t\t\tif target_obj then return target_obj.id end
\t\tend
\tend
"""

        target = f"""\
-- Quest target: smart/story id of the current stage.
local function {quest_id}_target(task_id, field, p, tsk)
	if field ~= "target" then return nil end
	local quest = QUESTS[{q}]
	if not quest then return nil end
	local stage = (tsk and tsk.stage) or 0
	local stage_data = quest.stages[stage]
{target_variants_code}\tlocal target_name = (stage_data and stage_data.target) or ""
\tif target_name ~= "" then
\t\tlocal target_id = resolve_target(target_name)
\t\tif target_id then return target_id end
\t\tlocal target_obj = resolve_alife_object(target_name)
\t\tif target_obj then return target_obj.id end
\tend
\tlocal target_squad = (stage_data and stage_data.target_squad) or ""
\tif target_squad ~= "" then
\t\tlocal squad = resolve_alife_object(target_squad)
\t\treturn squad and squad.id or nil
\tend
\tif tsk and tsk.task_giver_id and tsk.task_giver_id ~= 0 then
\t\treturn tsk.task_giver_id
\tend
\tlocal target_id = resolve_target(quest.npc)
\tif target_id then return target_id end
\tlocal target_obj = resolve_alife_object(quest.npc)
\treturn (target_obj and target_obj.id) or nil
end"""

        # Build descr function with optional descr_variants
        descr_variants_code = ""
        if data["stages"]:
            # Check if any stage has descr_variants
            has_descr_variants = any(
                stage_data.get("descr_variants")
                for stage_data in data["stages"].values()
            )
            if has_descr_variants:
                descr_variants_code = """\t-- Check descr_variants for current stage
\tlocal variants = (stage_data and stage_data.descr_variants) or {}
\tfor _, var in ipairs(variants) do
\t\tif eval_conditions(var.when, db.actor) then
\t\t\treturn var.key
\t\tend
\tend
"""

        descr = f"""\
-- Quest description: per-stage string id, falls back to the quest descr.
local function {quest_id}_descr(task_id, field, p, tsk)
	if field ~= "descr" then return nil end
	local quest = QUESTS[{q}]
	local stage = (tsk and tsk.stage) or 0
	local stage_data = quest and quest.stages[stage]
{descr_variants_code}\treturn (stage_data and stage_data.descr) or (quest and quest.descr) or nil
end"""

        advance = self._build_advance_code(quest_id, data)
        status = f"""\
-- Quest status: stage transitions and completion.
local function {quest_id}_status(tsk, task_id)
	if not (db.actor and tsk) then return nil end
	if task_id and task_id ~= {q} then return nil end
	local quest = QUESTS[{q}]
	if not quest then return nil end
	if (quest.world or quest.requires_warfare) and not is_warfare() then
		return nil
	end

	local now = time_global()
	if tsk.__quests_next and now < tsk.__quests_next then return nil end
	tsk.__quests_next = now + STATUS_THROTTLE_MS

	local stage = tsk.stage or 0
	local stage_data = quest.stages[stage]
	if not stage_data then return nil end

	-- Run stage start actions exactly once.
	local start_key = stage_key(quest, stage, "started")
	if vget(start_key, 0) == 0 then
		vset(start_key, 1)
		run_actions(stage_data.start_actions, db.actor, nil, {q}{stage_arg})
	end

	-- Quest items from on_start_actions are idempotent: if the actor lost
	-- the item (dropped it, died), give it back on the next status tick.
	if quest.complete_info == "" or not has_alife_info(quest.complete_info) then
		for _, item_spec in ipairs(stage_data.item_actions or {{}}) do
			if actor_item_count(item_spec.item, db.actor) < (item_spec.count or 1) then
				give_item(item_spec.item, item_spec.count, db.actor)
			end
		end
	end

{npc_item_status}	spawn_stage_for(quest, stage, stage_data)
	freeze_stage_for(quest, stage, stage_data)
	freeze_dyn_squads(quest)

	if stage_data.fail and #stage_data.fail > 0 then
		if eval_conditions(stage_data.fail, db.actor) then
			return "fail"
		end
	end

	if target_squad_dead(quest, stage) then
{advance}	end

	if stage_cleared(quest, stage, stage_data) then
{advance}	end

	if stage_data.complete and #stage_data.complete > 0 then
		if eval_conditions(stage_data.complete, db.actor) then
{advance}		end
	end

	if quest.return_stage >= 0 and stage == quest.return_stage then
		if reached_giver(quest, tsk) then
			return "complete"
		end
	end

	return nil
end"""

        start = f"""\
-- on_init effect: resets pstor state, gives the "taken" info and runs actions.
local function {quest_id}_start(actor, npc, p)
	local quest = QUESTS[{q}]
	if not (db.actor and quest) then return end
	if (quest.world or quest.requires_warfare) and not is_warfare() then
		return nil
	end

	for stage, stage_data in pairs(quest.stages) do
		vset(stage_key(quest, stage, "spawn"), 0)
		vset(stage_key(quest, stage, "enemy"), 0)
		vset(stage_key(quest, stage, "started"), 0)
		vset(stage_key(quest, stage, "target_seen"), 0)
{npc_item_reset}{story_reset}		local allies = (stage_data.capture and stage_data.capture.ally_count) or 0
		for i = 1, allies do
			vset(stage_key(quest, stage, "ally" .. i), 0)
		end
	end
	vset(quest.key_prefix .. "_said", 0)

	if quest.taken_info ~= "" then
		db.actor:give_info_portion(quest.taken_info)
	end
	run_actions(quest.init_actions, actor or db.actor, npc, {q}{extra_arg})
	sound_task()
	pda_tip(quest.msg_start)
	printf("[__SCRIPT_NAME__] %s started", {q})
end"""

        reward = f"""\
-- on_complete effect: money/item rewards, info portion and cleanup.
local function {quest_id}_reward(actor, npc, p)
	local quest = QUESTS[{q}]
	if not (db.actor and quest) then return end

	if quest.money and quest.money > 0 then
		give_money(quest.money, actor or db.actor)
	end
	if quest.item ~= "" then
		give_item(quest.item, quest.item_count, actor or db.actor)
	end
	if quest.complete_info ~= "" then
		db.actor:give_info_portion(quest.complete_info)
	end

	run_actions(quest.complete_actions, actor or db.actor, npc, {q}{extra_arg})
	for _, info in ipairs(quest.cleanup_infos or {{}}) do
		db.actor:disable_info_portion(info)
	end
	unmark_quest_squads(quest)
	vset(quest.key_prefix .. "_dyn_squad_cnt", 0)
	sound_task()
	pda_tip(quest.msg_reward)
	printf("[__SCRIPT_NAME__] %s reward given", {q})
end"""

        cleanup = f"""\
-- on_fail/on_cancel effect: releases squads and runs fail actions.
local function {quest_id}_cleanup(actor, npc, p)
	local quest = QUESTS[{q}]
	if not quest then return end

	unmark_quest_squads(quest)
	vset(quest.key_prefix .. "_dyn_squad_cnt", 0)
	run_actions(quest.fail_actions, actor or db.actor, npc, {q}{extra_arg})
	if db.actor and quest.taken_info ~= "" then
		db.actor:disable_info_portion(quest.taken_info)
	end
	for _, info in ipairs(quest.cleanup_infos or {{}}) do
		db.actor:disable_info_portion(info)
	end
	pda_tip(quest.msg_fail)
	printf("[__SCRIPT_NAME__] %s cleaned up", {q})
end"""

        accept = f"""\
-- Dialog effect: gives the task exactly once.
local function {quest_id}_accept(actor, npc, p)
	give_task({q}, actor, npc)
end"""

        turn_in = f"""\
-- Dialog effect: completes the task.
local function {quest_id}_turn_in(actor, npc, p)
	complete_task({q})
end"""

        keys.extend(
            [
                ("task_functor", f"{quest_id}_target", f"{quest_id}_target"),
                ("task_functor", f"{quest_id}_descr", f"{quest_id}_descr"),
                (
                    "task_status_functor",
                    f"{quest_id}_status",
                    f"{quest_id}_status",
                ),
                ("xr_effects", f"{quest_id}_start", f"{quest_id}_start"),
                ("xr_effects", f"{quest_id}_reward", f"{quest_id}_reward"),
                ("xr_effects", f"{quest_id}_cleanup", f"{quest_id}_cleanup"),
                ("dialogs", f"{quest_id}_accept", f"{quest_id}_accept"),
                ("dialogs", f"{quest_id}_turn_in", f"{quest_id}_turn_in"),
            ]
        )
        code = "\n\n".join(
            [target, descr, status, start, reward, cleanup, accept, turn_in]
        )
        return code, keys

    def _build_advance_code(self, quest_id: str, data: dict[str, Any]) -> str:
        """Формирует Lua-код перехода на следующий этап или завершения.

        Args:
            quest_id (str): ID квеста.
            data (dict[str, Any]): Данные квеста.

        Returns:
            str: Строки с отступом ``\\t\\t``, вставляемые в ``_status``.
        """
        return (
            "\t\tif stage >= quest.last_stage then\n"
            '\t\t\treturn "complete"\n'
            "\t\tend\n"
            "\t\ttsk.stage = stage + 1\n"
            "\t\tannounce(quest.key_prefix .. \"_said\", tsk.stage,\n"
            "\t\t\tstage_data.msg or \"\")\n"
            "\t\treturn nil\n"
        )

    def _build_dialog_functions(
        self,
        dialog_id: str,
        dialog: "Dialog",
        linked_quest_id: str | None,
        quest_data: dict[str, dict[str, Any]],
        needs_story: bool = False,
    ) -> tuple[str, list[tuple[str, str, str]]]:
        """Генерирует функции диалога и реплик.

        Диалоговые функции ``_can_take``/``_can_turn_in``/``_accept``/
        ``_turn_in`` регистрируются в ``dialogs``; функции реплик получают
        каноническую сигнатуру ``(actor, npc, p)``.

        Args:
            dialog_id (str): Канонический id диалога.
            dialog (Dialog): Модель диалога.
            linked_quest_id (str | None): Связанный квест.
            quest_data (dict[str, dict[str, Any]]): Данные квестов.
            needs_story (bool): Проект использует Story-действия.

        Returns:
            tuple[str, list[tuple[str, str, str]]]:
                Lua-код и список регистраций ``(table, key, function)``.
        """
        keys: list[tuple[str, str, str]] = []
        blocks: list[str] = []
        extra_arg = ", -1" if needs_story else ""

        # HasInfo/DontHasInfo уже вынесены в нативные XML-теги диалога.
        # Повторять их в _can_take нельзя (P1-9): это дублирует условие.
        condition_specs = [
            self._condition_spec(condition)
            for condition in dialog.preconditions
            if not isinstance(condition, (HasInfo, DontHasInfo))
        ]
        conditions_lua = self._to_lua(condition_specs, indent=1)
        linked = self._lua_string(linked_quest_id or "")
        linked_data = (
            quest_data.get(linked_quest_id) if linked_quest_id else None
        ) or {}
        complete_info = self._lua_string(
            str(linked_data.get("complete_info") or "")
        )
        done_info = self._lua_string(str(linked_data.get("done_info") or ""))
        requires_faction = self._lua_string(
            str(linked_data.get("requires_faction") or "")
        )
        requires_warfare = (
            "true" if linked_data.get("requires_warfare") else "false"
        )

        # Стадийная защита сдачи. Если известен этап возврата — требуем его.
        # Если этап возврата не задан, безусловно требуем последний этап:
        # диалог сдачи не должен открываться до полного прохождения квеста,
        # даже если у него есть собственный HasInfo (``taken`` — признак
        # выдачи, а не готовности).
        stage_guards = (
            "\tif quest.return_stage >= 0 and "
            "(tsk.stage or 0) < quest.return_stage then\n"
            "\t\treturn false\n"
            "\tend\n"
            "\tif quest.return_stage < 0 and "
            "(tsk.stage or 0) < (quest.last_stage or 0) then\n"
            "\t\treturn false\n"
            "\tend\n"
        )

        can_take = f"""\
-- Dialog availability: all dialog-level conditions plus "task not given".
-- A completed quest stays closed even after task_manager drops its task.
local function {dialog_id}_can_take(actor, npc, p)
	local linked = {linked}
	if linked ~= "" then
		local requires_warfare = {requires_warfare}
		if requires_warfare and not is_warfare() then
			return false
		end
		local requires_faction = {requires_faction}
		if requires_faction ~= "" and not is_actor_faction(requires_faction) then
			return false
		end
		local complete_info = {complete_info}
		if complete_info ~= "" and has_alife_info(complete_info) then
			return false
		end
		local done_info = {done_info}
		if done_info ~= "" and has_alife_info(done_info) then
			return false
		end
		local tm = task_manager and task_manager.get_task_manager()
		if tm and tm.task_info[linked] then return false end
	end
	return eval_conditions({conditions_lua}, actor or db.actor)
end"""

        can_turn_in = f"""\
-- Turn-in availability: the task exists and the return stage is reached.
local function {dialog_id}_can_turn_in(actor, npc, p)
	local linked = {linked}
	if linked == "" then return true end
	local quest = QUESTS[linked]
	if not quest then return true end
	local tm = task_manager and task_manager.get_task_manager()
	local tsk = tm and tm.task_info[linked]
	if not tsk then return false end
{stage_guards}	return true
end"""

        accept = f"""\
-- Dialog effect: gives the linked task.
local function {dialog_id}_accept(actor, npc, p)
	local linked = {linked}
	if linked ~= "" then give_task(linked, actor, npc) end
end"""

        turn_in = f"""\
-- Dialog effect: completes the linked task.
local function {dialog_id}_turn_in(actor, npc, p)
	local linked = {linked}
	if linked ~= "" then complete_task(linked) end
end"""

        blocks.extend([can_take, can_turn_in, accept, turn_in])
        keys.extend(
            [
                ("dialogs", f"{dialog_id}_can_take", f"{dialog_id}_can_take"),
                (
                    "dialogs",
                    f"{dialog_id}_can_turn_in",
                    f"{dialog_id}_can_turn_in",
                ),
                ("dialogs", f"{dialog_id}_accept", f"{dialog_id}_accept"),
                ("dialogs", f"{dialog_id}_turn_in", f"{dialog_id}_turn_in"),
            ]
        )

        for phrase_id in sorted(dialog.phrases):
            phrase = dialog.phrases[phrase_id]
            prefix = f"{dialog_id}_phrase_{phrase_id}"

            non_info_conditions = [
                self._condition_spec(condition)
                for condition in phrase.preconditions
                if not isinstance(condition, (HasInfo, DontHasInfo))
            ]
            if non_info_conditions:
                specs = self._to_lua(non_info_conditions, indent=1)
                blocks.append(
                    f"""\
-- Phrase {phrase_id} precondition.
local function {prefix}_precondition(actor, npc, p)
	return eval_conditions({specs}, actor or db.actor)
end"""
                )
                keys.append(
                    (
                        "dialogs",
                        f"{prefix}_precondition",
                        f"{prefix}_precondition",
                    )
                )

            # Один <action> на реплику: если действий несколько, все они
            # (включая give_task/complete_task) исполняются этой функцией
            # строго в порядке объявления в phrase.actions.
            if phrase_action_mode(phrase.actions) == "combined":
                lua_actions = [
                    action
                    for action in phrase.actions
                    if not isinstance(action, GiveInfo)
                ]
                specs = self._to_lua(
                    [self._action_spec(action) for action in lua_actions],
                    indent=1,
                )
                blocks.append(
                    f"""\
-- Phrase {phrase_id} action: merged actions of the phrase.
local function {prefix}_action(actor, npc, p)
	run_actions({specs}, actor or db.actor, npc, {linked}{extra_arg})
end"""
                )
                keys.append(
                    ("dialogs", f"{prefix}_action", f"{prefix}_action")
                )

        return "\n\n".join(blocks), keys

    def _build_registration(
        self,
        registrations: Sequence[tuple[str, str, str]],
        script_name: str,
    ) -> str:
        """Формирует ``register()`` и callback-обвязку модуля.

        Args:
            registrations (Sequence[tuple[str, str, str]]):
                Пары ``(engine_table, flat_key, function_name)``.
            script_name (str): Имя модуля для логов.

        Returns:
            str: Lua-код регистрации и автоматического вызова.
        """
        unique: dict[tuple[str, str], str] = {}
        for table, key, function_name in registrations:
            identity = (table, key)
            if identity in unique:
                logger.warning(
                    "Дублирующаяся регистрация %s[\"%s\"] пропущена.",
                    table,
                    key,
                )
                continue
            unique[identity] = function_name

        lines = [
            "-- ------------------------------------------------------------------",
            "-- Registration (module level, flat keys only)",
            "-- ------------------------------------------------------------------",
            "local function register()",
            "\tif registered then return end",
            "\tif not (task_functor and task_status_functor and xr_effects and dialogs) then",
            "\t\treturn",
            "\tend",
            "",
        ]
        for (table, key), function_name in unique.items():
            lines.append(
                f'\t{table}["{key}"] = {function_name}'
            )
        lines.extend(
            [
                "",
                "\tregistered = true",
                f'\tprintf("[{script_name}] task functors registered")',
                "end",
                "",
                "-- Called by axr_main's script scanner on a new game.",
                "function on_game_start()",
                "\tregister()",
                "end",
                "",
                "pcall(function()",
                '\tRegisterScriptCallback("on_game_load", function(binder) register() end)',
                '\tRegisterScriptCallback("actor_on_first_update", function(binder, delta) register() end)',
                "end)",
                "",
                "register()",
            ]
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Lua-сериализация
    # ------------------------------------------------------------------

    @staticmethod
    def _lua_string(value: Any) -> str:
        """Экранирует строку для вставки в Lua-исходник.

        Args:
            value (Any): Значение, которое нужно превратить в строковый
                литерал.

        Returns:
            str: Литерал в двойных кавычках с экранированными спецсимволами.
        """
        text = "" if value is None else str(value)
        escaped = (
            text.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace("\t", "\\t")
        )
        return f'"{escaped}"'

    def _to_lua(self, value: Any, *, indent: int = 0) -> str:
        """Сериализует Python-значение в Lua-литерал.

        Поддерживаются словари, списки/кортежи, строки, числа, булевы
        значения и ``None``.

        Args:
            value (Any): Сериализуемое значение.
            indent (int): Текущий уровень отступа (табуляции).

        Returns:
            str: Lua-литерал, пригодный для вставки в исходник.
        """
        pad = "\t" * indent
        child_pad = "\t" * (indent + 1)

        if value is None:
            return "nil"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, str):
            return self._lua_string(value)
        if isinstance(value, dict):
            if not value:
                return "{}"
            lines = ["{"]
            for key, item in value.items():
                if isinstance(key, int):
                    key_text = f"[{key}]"
                elif isinstance(key, str) and _is_lua_identifier(key):
                    key_text = key
                else:
                    key_text = f"[{self._lua_string(key)}]"
                lines.append(
                    f"{child_pad}{key_text} = "
                    f"{self._to_lua(item, indent=indent + 1)},"
                )
            lines.append(f"{pad}}}")
            return "\n".join(lines)
        if isinstance(value, (list, tuple)):
            if not value:
                return "{}"
            lines = ["{"]
            for item in value:
                lines.append(
                    f"{child_pad}{self._to_lua(item, indent=indent + 1)},"
                )
            lines.append(f"{pad}}}")
            return "\n".join(lines)
        raise TypeError(f"Не удалось сериализовать в Lua: {type(value).__name__}")


def _is_lua_identifier(value: str) -> bool:
    """Проверяет, является ли строка допустимым Lua-идентификатором.

    Args:
        value (str): Проверяемая строка.

    Returns:
        bool: ``True``, если строка начинается с буквы/``_`` и содержит только
            буквы, цифры и ``_``, а также не является зарезервированным словом.
    """
    if not value or value in _LUA_RESERVED:
        return False
    if not (value[0].isalpha() or value[0] == "_"):
        return False
    return all(char.isalnum() or char == "_" for char in value)


__all__ = ["LuaGenerator"]
