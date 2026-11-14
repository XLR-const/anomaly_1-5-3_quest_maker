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
    SetTarget,
    SmartOwner,
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
end

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
local function give_task(task_id, npc)
	local tm = task_manager and task_manager.get_task_manager()
	if not tm then
		printe("[__SCRIPT_NAME__] ! task_manager is nil")
		return
	end
	if tm.task_info[task_id] then return end

	-- Normalize the speaker to an actor-alife object first; dialogs.who_is_npc
	-- also handles the case when the engine passes a non-NPC object.
	local speaker = npc
	if dialogs and dialogs.who_is_npc then
		local ok, value = pcall(dialogs.who_is_npc, db.actor, npc)
		if ok and value then speaker = value end
	end

	local giver_id = nil
	if speaker then
		local ok, value = pcall(function() return speaker:id() end)
		if ok then giver_id = value end
	end
	if not giver_id then
		local quest = QUESTS[task_id]
		if quest and quest.npc ~= "" then
			giver_id = resolve_target(quest.npc)
		end
	end
	-- 0 is truthy in Lua: passing it makes task_manager treat the actor as
	-- the giver and breaks the quest marker. Pass nil instead.
	if giver_id == 0 then giver_id = nil end
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

-- Executes a list of serialized action specs in order.
local function run_actions(actions, actor, npc, quest_id)
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
			give_task(spec.task, npc)
		elseif kind == "complete_task" then
			complete_task(spec.task)
		end
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
        blocks.append(self._build_helpers(module_name))

        for quest_id, data in quest_data.items():
            quest = quests[quest_id]
            try:
                code, keys = self._build_quest_functions(quest_id, quest, data)
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
                    dialog_id, dialog, linked, quest_data
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

    def _action_spec(self, action: Any) -> dict[str, Any]:
        """Преобразует Pydantic-действие в словарь для Lua.

        Args:
            action (Any): Действие модели.

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
            return {
                "kind": "spawn_squad",
                "squad": action.squad_alias,
                "smart": action.smart_alias,
            }
        if isinstance(action, SetTarget):
            return {
                "kind": "set_target",
                "squad": action.squad_alias,
                "smart": action.smart_alias,
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
            start_actions: list[dict[str, Any]] = []
            item_actions: list[dict[str, Any]] = []
            for action in stage.on_start_actions:
                spec = self._action_spec(action)
                if isinstance(action, GiveItem):
                    item_actions.append(spec)
                else:
                    start_actions.append(spec)
            stages[stage_id] = {
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
            "taken_info": quest.taken_info or "",
            "complete_info": quest.complete_info or "",
            "cleanup_infos": list(getattr(quest, "cleanup_infos", []) or []),
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

    def _build_helpers(self, script_name: str) -> str:
        """Подставляет имя модуля и константы в шаблон общих хелперов.

        Args:
            script_name (str): Имя модуля для логов.

        Returns:
            str: Lua-код generic-хелперов.
        """
        return (
            _HELPERS_TEMPLATE.replace("__SCRIPT_NAME__", script_name)
            .replace("__PDA_SOUND__", DEFAULT_PDA_SOUND)
            .replace("__STATUS_THROTTLE__", str(DEFAULT_STATUS_THROTTLE_MS))
            .replace("__RETURN_DISTANCE__", str(DEFAULT_RETURN_DISTANCE))
            .strip()
        )

    def _build_quest_functions(
        self, quest_id: str, quest: "Quest", data: dict[str, Any]
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

        Returns:
            tuple[str, list[tuple[str, str, str]]]:
                Lua-код и список регистраций ``(table, key, function)``.
        """
        q = self._lua_string(quest_id)
        keys: list[tuple[str, str, str]] = []

        target = f"""\
-- Quest target: smart/story id of the current stage.
local function {quest_id}_target(task_id, field, p, tsk)
	if field ~= "target" then return nil end
	local quest = QUESTS[{q}]
	if not quest then return nil end
	local stage = (tsk and tsk.stage) or 0
	local stage_data = quest.stages[stage]
	local target_name = (stage_data and stage_data.target) or ""
	if target_name ~= "" then
		local target_id = resolve_target(target_name)
		if target_id then return target_id end
		local target_obj = resolve_alife_object(target_name)
		if target_obj then return target_obj.id end
	end
	local target_squad = (stage_data and stage_data.target_squad) or ""
	if target_squad ~= "" then
		local squad = resolve_alife_object(target_squad)
		return squad and squad.id or nil
	end
	if tsk and tsk.task_giver_id and tsk.task_giver_id ~= 0 then
		return tsk.task_giver_id
	end
	return resolve_target(quest.npc)
end"""

        descr = f"""\
-- Quest description: per-stage string id, falls back to the quest descr.
local function {quest_id}_descr(task_id, field, p, tsk)
	if field ~= "descr" then return nil end
	local quest = QUESTS[{q}]
	local stage = (tsk and tsk.stage) or 0
	local stage_data = quest and quest.stages[stage]
	return (stage_data and stage_data.descr) or (quest and quest.descr) or nil
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
		run_actions(stage_data.start_actions, db.actor, nil, {q})
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

	spawn_stage_for(quest, stage, stage_data)
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
		local allies = (stage_data.capture and stage_data.capture.ally_count) or 0
		for i = 1, allies do
			vset(stage_key(quest, stage, "ally" .. i), 0)
		end
	end
	vset(quest.key_prefix .. "_said", 0)
	vset(quest.key_prefix .. "_dyn_squad_cnt", 0)

	if quest.taken_info ~= "" then
		db.actor:give_info_portion(quest.taken_info)
	end
	run_actions(quest.init_actions, actor or db.actor, npc, {q})
	sound_task()
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

	run_actions(quest.complete_actions, actor or db.actor, npc, {q})
	for _, info in ipairs(quest.cleanup_infos or {{}}) do
		db.actor:disable_info_portion(info)
	end
	unmark_quest_squads(quest)
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
	run_actions(quest.fail_actions, actor or db.actor, npc, {q})
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
	give_task({q}, npc)
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

        Returns:
            tuple[str, list[tuple[str, str, str]]]:
                Lua-код и список регистраций ``(table, key, function)``.
        """
        keys: list[tuple[str, str, str]] = []
        blocks: list[str] = []

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
	if quest.return_stage >= 0 and (tsk.stage or 0) < quest.return_stage then
		return false
	end
	return true
end"""

        accept = f"""\
-- Dialog effect: gives the linked task.
local function {dialog_id}_accept(actor, npc, p)
	local linked = {linked}
	if linked ~= "" then give_task(linked, npc) end
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
	run_actions({specs}, actor or db.actor, npc, {linked})
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
